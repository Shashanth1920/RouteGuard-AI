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


def test_agent_route_never_calls_an_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_llm", _fake_call_llm(calls))
    result = llm.get_answer("agent", "What's 847 times 23?")
    assert calls == []
    assert result["error"] == "agent not built yet"


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
