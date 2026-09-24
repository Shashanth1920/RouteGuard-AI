"""File: app/llm/client.py. call_llm() sends one message to one model and
reports back what happened (answer, tokens, time, cost). get_answer() maps
a router route to that call: which model(s) to try, and what to do for
routes that shouldn't touch an LLM at all (human_review, agent)."""
import time

import requests
from pydantic import BaseModel

from app.agents.agent import run_agent
from app.config import (
    LLM_MAX_TOKENS,
    LLM_SYSTEM_PROMPT,
    LLM_TIMEOUT,
    OPENROUTER_API_KEY,
    SMALL_LLM_MODEL,
    STRONG_LLM_MODEL,
)

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SESSION = requests.Session()


class LLMAnswer(BaseModel):
    answer: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost: float
    llm_time_taken: float


def call_llm(model: str, message: str) -> LLMAnswer:
    start = time.time()
    resp = SESSION.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={
            "model": model,
            "max_tokens": LLM_MAX_TOKENS,
            "usage": {"include": True},
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        },
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data["usage"]
    return LLMAnswer(
        answer=data["choices"][0]["message"]["content"],
        model_used=model,
        input_tokens=usage["prompt_tokens"],
        output_tokens=usage["completion_tokens"],
        cost=usage["cost"],
        llm_time_taken=time.time() - start,
    )


# Fields always present on a get_answer() result, so the API response model
# can be built with **answer_dict regardless of which branch ran.
_EMPTY = {
    "answer": None, "model_used": None, "input_tokens": None,
    "output_tokens": None, "cost": None, "llm_time_taken": None, "error": None,
    "tools_used": None, "steps": None, "gate_log": None,
}


def get_answer(route: str, message: str, complexity_label: str = "simple") -> dict:
    if route == "human_review":
        return {**_EMPTY, "error": "waiting for human approval"}
    if route == "agent":
        result = run_agent(message, complexity_label)
        return {
            **_EMPTY,
            "answer": result["answer"],
            "model_used": result["model_used"],
            "tools_used": result["tools_used"],
            "gate_log": result["gate_log"],
            "steps": result["steps"],
            "llm_time_taken": result["agent_time_taken"],
        }

    model = SMALL_LLM_MODEL if route == "small_llm" else STRONG_LLM_MODEL
    try:
        return {**_EMPTY, **call_llm(model, message).model_dump()}
    except (requests.RequestException, KeyError, IndexError):
        pass

    if model == SMALL_LLM_MODEL:
        try:
            return {**_EMPTY, **call_llm(STRONG_LLM_MODEL, message).model_dump()}
        except (requests.RequestException, KeyError, IndexError):
            pass

    return {**_EMPTY, "error": "LLM call failed"}
