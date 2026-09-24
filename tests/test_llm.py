"""Fake-LLM tests - no network, no API key. Proves route -> model wiring
and the human_review/agent "never call an LLM" guarantee."""
import requests

from app.config import SMALL_LLM_MODEL, STRONG_LLM_MODEL
from app.llm import client as llm


def _fake_call_llm(calls, answer="ok", fail_models=()):
    def _fake(model, message):
        calls.append(model)
        if model in fail_models:
            raise requests.ConnectionError("simulated failure")
        return llm.LLMAnswer(
            answer=answer, model_used=model, input_tokens=1,
            output_tokens=1, cost=0.0001, llm_time_taken=0.1,
        )
    return _fake


def test_small_llm_route_calls_the_cheap_model(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls))
    result = llm.get_answer("small_llm", "Tell me a joke")
    assert calls == [SMALL_LLM_MODEL]
    assert result["model_used"] == SMALL_LLM_MODEL
    assert result["error"] is None


def test_strong_llm_route_calls_the_strong_model(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls))
    result = llm.get_answer("strong_llm", "Explain the risks in this report")
    assert calls == [STRONG_LLM_MODEL]
    assert result["model_used"] == STRONG_LLM_MODEL


def test_human_review_never_calls_an_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls))
    result = llm.get_answer("human_review", "Delete all users")
    assert calls == []
    assert result["answer"] is None
    assert result["error"] == "waiting for human approval"


def test_agent_route_delegates_to_run_agent_not_call_llm(monkeypatch):
    """get_answer() must never call the plain call_llm() path for 'agent' -
    it hands off to run_agent() instead. See test_agent.py for the agent's
    own tool-use behavior, tested separately with a scripted fake LLM."""
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls))
    monkeypatch.setattr(
        llm, "run_agent",
        lambda message, complexity_label: {
            "answer": "19481", "model_used": SMALL_LLM_MODEL,
            "tools_used": [{"name": "calculator", "input": {}, "output": {}}],
            "gate_log": [{"tool": "calculator", "input": {}, "result": "ALLOW", "reason": "ok"}],
            "steps": 1, "agent_time_taken": 0.2,
            "input_tokens": 42, "output_tokens": 7, "cost": 0.0005,
        },
    )
    result = llm.get_answer("agent", "What's 847 times 23?")
    assert calls == []
    assert result["answer"] == "19481"
    assert result["steps"] == 1
    assert result["tools_used"][0]["name"] == "calculator"
    assert result["input_tokens"] == 42
    assert result["output_tokens"] == 7
    assert result["cost"] == 0.0005


def test_small_llm_failure_backs_up_to_strong_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls, fail_models=(SMALL_LLM_MODEL,)))
    result = llm.get_answer("small_llm", "Tell me a joke")
    assert calls == [SMALL_LLM_MODEL, STRONG_LLM_MODEL]
    assert result["model_used"] == STRONG_LLM_MODEL
    assert result["error"] is None


def test_both_models_failing_returns_clean_error(monkeypatch):
    calls = []
    monkeypatch.setattr(
        llm, "call_llm",
        _fake_call_llm(calls, fail_models=(SMALL_LLM_MODEL, STRONG_LLM_MODEL)),
    )
    result = llm.get_answer("small_llm", "Tell me a joke")
    assert calls == [SMALL_LLM_MODEL, STRONG_LLM_MODEL]
    assert result["answer"] is None
    assert result["error"] == "LLM call failed"


def test_strong_llm_failure_has_no_backup(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls, fail_models=(STRONG_LLM_MODEL,)))
    result = llm.get_answer("strong_llm", "Explain the risks in this report")
    assert calls == [STRONG_LLM_MODEL]
    assert result["error"] == "LLM call failed"
