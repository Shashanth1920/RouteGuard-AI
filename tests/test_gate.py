"""Fake-Jev tests for the Safety Gate - no network, no API key needed.
Mirrors tests/test_decisions.py's FakeResponse pattern."""
import requests

from app.safety import gate


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _fake_answers(destructive=0.05, matches=0.95):
    return {"answers": {"destructive": {"noul": destructive}, "matches": {"noul": matches}}}


def test_calculator_call_is_allowed(monkeypatch):
    monkeypatch.setattr(
        gate.SESSION, "post",
        lambda *a, **k: FakeResponse(_fake_answers(destructive=0.03, matches=0.97)),
    )
    result = gate.check_gate("calculator", {"expression": "847 * 23"}, "What is 847 * 23?", destructive_label=False)
    assert result.result == "ALLOW"


def test_destructive_label_always_needs_approval_even_when_jev_says_low_risk(monkeypatch):
    # Jev's own destructive score is low here on purpose - the registry's
    # fixed label must still win. "Never automatic" means never, not "only
    # when Jev agrees."
    monkeypatch.setattr(
        gate.SESSION, "post",
        lambda *a, **k: FakeResponse(_fake_answers(destructive=0.10, matches=0.95)),
    )
    result = gate.check_gate("delete_user", {"user_id": 3}, "Delete user 3", destructive_label=True)
    assert result.result == "NEEDS_APPROVAL"
    assert "destructive" in result.reason


def test_mismatch_blocks_regardless_of_destructive_label(monkeypatch):
    # The injection shape: user asked to search, agent proposes delete_user.
    monkeypatch.setattr(
        gate.SESSION, "post",
        lambda *a, **k: FakeResponse(_fake_answers(destructive=0.95, matches=0.02)),
    )
    result = gate.check_gate(
        "delete_user", {"user_id": 3}, "Search for info about our users", destructive_label=True,
    )
    assert result.result == "BLOCK"
    assert "match" in result.reason


def test_jev_flags_this_specific_call_as_risky_even_without_a_destructive_label(monkeypatch):
    # Same tool, different scope: updating every row instead of one. The
    # registry label alone can't see this - only Jev looking at the
    # specific call can.
    monkeypatch.setattr(
        gate.SESSION, "post",
        lambda *a, **k: FakeResponse(_fake_answers(destructive=0.90, matches=0.95)),
    )
    result = gate.check_gate(
        "update_all_product_prices", {"category": "electronics"},
        "Update this product's price", destructive_label=False,
    )
    assert result.result == "NEEDS_APPROVAL"


def test_low_risk_matching_non_destructive_call_is_allowed(monkeypatch):
    monkeypatch.setattr(
        gate.SESSION, "post",
        lambda *a, **k: FakeResponse(_fake_answers(destructive=0.05, matches=0.90)),
    )
    result = gate.check_gate("read_user", {"user_id": 3}, "Show me user 3", destructive_label=False)
    assert result.result == "ALLOW"


def test_jev_error_needs_approval_not_allow(monkeypatch):
    def _raise(*a, **k):
        raise requests.ConnectionError("no network")
    monkeypatch.setattr(gate.SESSION, "post", _raise)
    result = gate.check_gate("calculator", {"expression": "1+1"}, "what is 1+1", destructive_label=False)
    assert result.result == "NEEDS_APPROVAL"
    assert result.is_fallback is True


def test_malformed_jev_response_needs_approval_not_allow(monkeypatch):
    monkeypatch.setattr(gate.SESSION, "post", lambda *a, **k: FakeResponse({"answers": {}}))
    result = gate.check_gate("calculator", {"expression": "1+1"}, "what is 1+1", destructive_label=False)
    assert result.result == "NEEDS_APPROVAL"
    assert result.is_fallback is True


def test_every_result_has_a_nonempty_reason(monkeypatch):
    for destructive, matches, label in [(0.05, 0.95, False), (0.05, 0.95, True), (0.9, 0.02, False)]:
        monkeypatch.setattr(
            gate.SESSION, "post",
            lambda *a, destructive=destructive, matches=matches, **k: FakeResponse(_fake_answers(destructive, matches)),
        )
        result = gate.check_gate("some_tool", {}, "do something", destructive_label=label)
        assert result.reason
