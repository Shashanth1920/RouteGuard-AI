"""File 2: the receptionist. Makes 1 Jev call and fills in the Decision
form. Reports facts only - it never decides where a request goes, that's
the router's job (see the module docstring's hospital analogy: the
receptionist writes "92% emergency", the hospital rules send the patient
to the ER).

Fail safe: if Jev times out, errors, or sends back something we can't
parse, we don't guess. We return a form that says high risk, high
complexity, needs a tool - never a silent "looks fine"."""
import time

import requests
from pydantic import ValidationError

from app.config import JEV_MODEL, JEV_TIMEOUT, OPENROUTER_API_KEY
from app.decision.schemas import Decision

API_URL = "https://openrouter.ai/api/alpha/decisions"
SESSION = requests.Session()

COMPLEXITY_LABELS = ["simple", "moderate", "complex"]

# The 4 questions, defined once. Includes the fixes from Part 2's review:
# needs_tool spells out that arithmetic counts (Jev is weak at math itself),
# and intent has a 6th option, "action", for real-world effects like moving
# money or mass-emailing.
QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "What is the intent of this message?",
        "criteria": {
            "calculation": "The user wants a math computation or numeric result.",
            "coding": "The user wants code written, debugged, reviewed, or explained.",
            "search": "The user wants current facts, news, or information looked up.",
            "database action": "The user wants data inserted, updated, or deleted in a database.",
            "action": "The user wants something done that has a real-world effect "
                      "outside the conversation - moving money, sending a message or "
                      "email to many people, or triggering an external system.",
            "general": "General conversation, summaries, or anything that doesn't fit the others.",
        },
    },
    "complexity": {
        "type": "score",
        "instructions": "How complex is it to fulfill this request?",
        "criteria": [
            "Simple: a single fact, a quick reply, or one obvious step with no "
            "real reasoning or domain knowledge required.",
            "Moderate: a few steps, some domain knowledge, or careful wording "
            "needed to get right.",
            "Complex: multi-step reasoning, deep domain knowledge, or high "
            "precision needed - getting it wrong is easy.",
        ],
    },
    "risk": {
        "type": "noul",
        "instructions": "Could carrying out this request cause irreversible harm?",
        "criteria": {
            "true": "The action is destructive or hard to undo: deleting or dropping "
                    "data, moving money, or messaging a large number of people at once.",
            "false": "The action is safe and reversible, or purely informational - "
                     "nothing is destroyed, spent, or sent at scale.",
        },
    },
    "needs_tool": {
        "type": "noul",
        "instructions": "Does answering this require calling an external tool or "
                         "system, rather than just replying in natural language?",
        "criteria": {
            "true": "Requires running code, querying or modifying a database, "
                    "searching the web, or computing an exact numeric result - "
                    "this includes ANY arithmetic or math, even something that "
                    "looks simple like 847 x 23, since the model itself is "
                    "unreliable at math and must hand it to a calculator.",
            "false": "Answerable from conversation or general knowledge alone, "
                     "no external system needed.",
        },
    },
}


def _complexity_label(score: float) -> str:
    """1.27 -> round to 1 -> 'moderate'. Clamped to the 0-2 legend range."""
    index = max(0, min(2, round(score)))
    return COMPLEXITY_LABELS[index]


def _fail_safe(elapsed: float) -> Decision:
    return Decision(
        intent="general",
        intent_confidence=0.0,
        complexity_score=2.0,
        complexity_label="complex",
        risk=1.0,
        needs_tool=1.0,
        time_taken=elapsed,
    )


def classify(message: str) -> Decision:
    """One Jev call, all 4 questions. Returns a filled Decision, or the
    fail-safe Decision if anything goes wrong."""
    payload = {
        "model": JEV_MODEL,
        "state": {"message": message},
        "questions": QUESTIONS,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    start = time.time()
    try:
        response = SESSION.post(API_URL, headers=headers, json=payload, timeout=JEV_TIMEOUT)
        elapsed = time.time() - start
        response.raise_for_status()
        answers = response.json()["answers"]
        complexity_score = answers["complexity"]["score"]

        return Decision(
            intent=answers["intent"]["choice"],
            intent_confidence=answers["intent"]["confidence"],
            complexity_score=complexity_score,
            complexity_label=_complexity_label(complexity_score),
            risk=answers["risk"]["noul"],
            needs_tool=answers["needs_tool"]["noul"],
            time_taken=elapsed,
        )
    except (requests.RequestException, KeyError, ValueError, ValidationError):
        elapsed = time.time() - start
        return _fail_safe(elapsed)
