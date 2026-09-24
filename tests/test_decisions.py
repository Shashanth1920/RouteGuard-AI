"""Fake-Jev tests run with no network and no API key - fast and free.
The real-Jev tests at the bottom are skipped automatically if
OPENROUTER_API_KEY isn't set."""
import os

import pytest
import requests

from app.decision import jev_classifier as jc

REAL_KEY = os.getenv("OPENROUTER_API_KEY")


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _fake_answers(intent="calculation", confidence=0.95, complexity=0.3, risk=0.01, needs_tool=0.8):
    return {
        "answers": {
            "intent": {"choice": intent, "confidence": confidence},
            "complexity": {"score": complexity},
            "risk": {"noul": risk},
            "needs_tool": {"noul": needs_tool},
        }
    }


# --- fake Jev: normal response fills the form correctly ---------------------

def test_classify_fills_form_from_normal_response(monkeypatch):
    fake = _fake_answers(intent="calculation", confidence=0.95, complexity=0.3, risk=0.01, needs_tool=0.8)
    monkeypatch.setattr(jc.SESSION, "post", lambda *a, **k: FakeResponse(fake))

    decision = jc.classify("What is 2+2?")

    assert decision.intent == "calculation"
    assert decision.intent_confidence == 0.95
    assert decision.complexity_score == 0.3
    assert decision.complexity_label == "simple"
    assert decision.risk == 0.01
    assert decision.needs_tool == 0.8
    assert decision.is_fallback is False
    assert isinstance(decision.time_taken, float)


# --- fake Jev: errors/timeouts return the safe form, never "low risk" -------
# and are marked is_fallback=True so they're never confused with a real
# risk=1.0 assessment later, in logs or evaluation.

def test_classify_returns_fail_safe_on_timeout(monkeypatch):
    def raise_timeout(*a, **k):
        raise requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(jc.SESSION, "post", raise_timeout)
    decision = jc.classify("Delete the production database.")

    assert decision.risk == 1.0
    assert decision.needs_tool == 1.0
    assert decision.complexity_label == "complex"
    assert decision.complexity_score == 2.0
    assert decision.is_fallback is True
    assert decision.intent == "unknown"


def test_classify_returns_fail_safe_on_http_error(monkeypatch):
    monkeypatch.setattr(jc.SESSION, "post", lambda *a, **k: FakeResponse({}, status_code=401))
    decision = jc.classify("Anything")

    assert decision.risk == 1.0
    assert decision.complexity_label == "complex"
    assert decision.is_fallback is True
    assert decision.intent == "unknown"


def test_classify_returns_fail_safe_on_malformed_json(monkeypatch):
    # missing the "risk" question entirely - a real but broken response
    monkeypatch.setattr(jc.SESSION, "post", lambda *a, **k: FakeResponse({"answers": {}}))
    decision = jc.classify("Anything")

    assert decision.risk == 1.0
    assert decision.needs_tool == 1.0
    assert decision.is_fallback is True
    assert decision.intent == "unknown"


def test_fail_safe_never_reports_low_risk(monkeypatch):
    monkeypatch.setattr(jc.SESSION, "post", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    decision = jc.classify("test")
    assert decision.risk >= 0.5  # fail safe must never look "low risk" by accident
    assert decision.is_fallback is True  # and must never be confused with a real risk=1.0 verdict


# --- complexity number -> label -----------------------------------------------

@pytest.mark.parametrize("score,label", [(0.3, "simple"), (1.0, "moderate"), (1.8, "complex")])
def test_complexity_label_conversion(score, label):
    assert jc._complexity_label(score) == label


# --- real Jev: a handful of live calls to check the real thing works --------

REAL_TEST_SENTENCES = [
    "What is 12 times 12?",
    "Delete the customers table.",
    "How are you today?",
    "Write a function to sort a list.",
    "Send $500 to this bank account.",
]


@pytest.mark.skipif(not REAL_KEY, reason="requires OPENROUTER_API_KEY in .env")
@pytest.mark.parametrize("sentence", REAL_TEST_SENTENCES)
def test_classify_real_sentences(sentence):
    decision = jc.classify(sentence)

    assert decision.intent in {"calculation", "coding", "search", "database action", "action", "general"}
    assert 0 <= decision.risk <= 1
    assert 0 <= decision.needs_tool <= 1
    assert decision.complexity_label in {"simple", "moderate", "complex"}
    assert decision.time_taken > 0
    assert decision.is_fallback is False  # a genuine answer, not a masked failure
