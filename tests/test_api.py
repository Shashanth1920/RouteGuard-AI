"""API tests use a fake classify() - no network, no API key needed."""
import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.decision.schemas import Decision
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_real_logging(monkeypatch):
    """These tests use a fake classify() and shouldn't also write rows into
    the real database - that's app/db/test_logging.py's job, against a
    dedicated test database."""
    monkeypatch.setattr(routes, "save_request", lambda *a, **k: None)


def _fake_classify_factory(**overrides):
    defaults = dict(
        intent="calculation", intent_confidence=0.95,
        complexity_score=0.3, complexity_label="simple",
        risk=0.01, needs_tool=0.1, time_taken=0.5, is_fallback=False,
    )
    defaults.update(overrides)

    def _fake_classify(message):
        return Decision(**defaults)

    return _fake_classify


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_normal_message_returns_route_and_reason(monkeypatch):
    monkeypatch.setattr(routes, "classify", _fake_classify_factory())
    resp = client.post("/v1/route", json={"message": "What is 2+2?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "small_llm"
    assert body["reason"]
    assert "request_id" in body


def test_empty_message_is_rejected():
    resp = client.post("/v1/route", json={"message": ""})
    assert resp.status_code == 422


def test_too_long_message_is_rejected():
    resp = client.post("/v1/route", json={"message": "a" * 5001})
    assert resp.status_code == 422


def test_fake_jev_failure_still_routes_to_human_review(monkeypatch):
    monkeypatch.setattr(
        routes, "classify",
        _fake_classify_factory(
            intent="unknown", intent_confidence=0.0,
            complexity_score=2.0, complexity_label="complex",
            risk=1.0, needs_tool=1.0, is_fallback=True,
        ),
    )
    resp = client.post("/v1/route", json={"message": "anything"})
    assert resp.status_code == 200
    assert resp.json()["route"] == "human_review"
