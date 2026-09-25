"""Part 7 Step 3 - the second doctor. Same 4 questions Jev answers, same
instructions/criteria (imported directly from app/decision/jev_classifier.py
so neither decider gets an easier prompt or a different definition of
"risky"), same output shape (a Decision), so app/routing/router.py runs
completely unchanged on either one's output. Answered by SMALL_LLM_MODEL
(Luna) via OpenRouter chat completions with strict structured JSON output,
not Jev's own Decisions API.

Fail-safe policy matches Jev's classify(): any network/parse failure
returns the same "treat it as an emergency" Decision, never a silent
guess - so a baseline failure doesn't accidentally look safer than a
Jev failure would.
"""
import json
import time

import requests
from pydantic import ValidationError

from app.config import LLM_TIMEOUT, OPENROUTER_API_KEY, SMALL_LLM_MODEL
from app.decision.jev_classifier import QUESTIONS, _complexity_label, _fail_safe
from app.decision.schemas import Decision

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SESSION = requests.Session()

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": list(QUESTIONS["intent"]["criteria"])},
                "intent_confidence": {"type": "number"},
                "complexity_score": {"type": "number"},
                "risk": {"type": "number"},
                "needs_tool": {"type": "number"},
            },
            "required": ["intent", "intent_confidence", "complexity_score", "risk", "needs_tool"],
            "additionalProperties": False,
        },
    },
}


def _build_prompt() -> str:
    """Renders app/decision/jev_classifier.py's own QUESTIONS dict as text -
    imported, not retyped, so the 2 deciders can never quietly drift apart."""
    lines = [
        "Answer these 4 questions about the user's message. These are the exact "
        "same definitions the production decision model uses - answer them the "
        "same way it would, not with an easier or looser reading.",
        "",
    ]
    for name, q in QUESTIONS.items():
        lines.append(f"## {name}: {q['instructions']}")
        criteria = q["criteria"]
        if isinstance(criteria, dict):
            for key, desc in criteria.items():
                lines.append(f"- {key}: {desc}")
        else:
            for desc in criteria:
                lines.append(f"- {desc}")
        lines.append("")
    lines += [
        "Return JSON with:",
        "- intent: one of the intent choices above, exactly as spelled",
        "- intent_confidence: 0-1, how sure you are about intent",
        "- complexity_score: 0=simple, 1=moderate, 2=complex (fractional values allowed)",
        "- risk: 0-1, how strongly the risk criteria's 'true' case applies",
        "- needs_tool: 0-1, how strongly the needs_tool criteria's 'true' case applies",
    ]
    return "\n".join(lines)


SYSTEM_PROMPT = _build_prompt()


def _post_with_retry(message: str, retries: int = 8):
    """OpenRouter 429s (rate limit) and 402s ("can only afford N tokens",
    despite plenty of total account balance - a burst-spend-velocity limit,
    not a real balance shortage, confirmed live) both show up under this
    evaluation's request volume. A single fail-safe on either isn't a real
    capability comparison, so retry with backoff before giving up for real."""
    resp = None
    for attempt in range(retries):
        resp = SESSION.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": SMALL_LLM_MODEL,
                "max_tokens": 300,  # a 5-field JSON reply never needs more; the
                                    # model's default max (65536) exceeds this
                                    # account's remaining credit and 402s.
                "usage": {"include": True},
                "response_format": RESPONSE_FORMAT,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
            },
            timeout=LLM_TIMEOUT,
        )
        if resp.status_code in (429, 402) and attempt < retries - 1:
            wait = float(resp.headers.get("Retry-After", 5 * (attempt + 1)))
            time.sleep(wait)
            continue
        return resp
    return resp


def classify(message: str) -> Decision:
    """Same signature and same fail-safe behavior as jev_classifier.classify().
    Decision.jev_cost/jev_input_tokens/jev_output_tokens are reused here to
    carry this call's real cost/tokens - same fields, different decider,
    so evaluation code doesn't need a second cost field just for this."""
    start = time.monotonic()
    try:
        resp = _post_with_retry(message)
        elapsed = time.monotonic() - start
        resp.raise_for_status()
        data = resp.json()
        answer = json.loads(data["choices"][0]["message"]["content"])
        usage = data.get("usage", {})

        return Decision(
            intent=answer["intent"],
            intent_confidence=max(0.0, min(1.0, answer["intent_confidence"])),
            complexity_score=answer["complexity_score"],
            complexity_label=_complexity_label(answer["complexity_score"]),
            risk=max(0.0, min(1.0, answer["risk"])),
            needs_tool=max(0.0, min(1.0, answer["needs_tool"])),
            time_taken=elapsed,
            jev_input_tokens=usage.get("prompt_tokens", 0),
            jev_output_tokens=usage.get("completion_tokens", 0),
            jev_cost=usage.get("cost", 0.0),
        )
    except (requests.RequestException, KeyError, ValueError, ValidationError):
        elapsed = time.monotonic() - start
        return _fail_safe(elapsed)
