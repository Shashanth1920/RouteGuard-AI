"""Uses a dedicated test database (DB_TEST_NAME), never the real one. If
Postgres isn't reachable at all, every test here is skipped rather than
failing the whole suite - the fake-everything tests elsewhere don't need a
database, only these do."""
import pytest

from app.config import DB_TEST_NAME, OPENROUTER_API_KEY, TAVILY_API_KEY
from app.db import logging as db_logging
from app.decision.schemas import Decision
from app.routing.router import RouteResult

try:
    db_logging.init_db(DB_TEST_NAME)
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not DB_AVAILABLE, reason=f"Postgres test database '{DB_TEST_NAME}' not reachable")


@pytest.fixture(autouse=True)
def _clean_tables():
    conn = db_logging.get_connection(DB_TEST_NAME)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE tool_calls, requests")
    conn.close()
    yield


def _decision(**overrides):
    defaults = dict(
        intent="calculation", intent_confidence=0.95, complexity_score=0.3,
        complexity_label="simple", risk=0.01, needs_tool=0.1, time_taken=0.4, is_fallback=False,
    )
    defaults.update(overrides)
    return Decision(**defaults)


def _route_result(**overrides):
    defaults = dict(route="small_llm", reason="low risk, confident, not complex, no tool needed", rule=6)
    defaults.update(overrides)
    return RouteResult(**defaults)


def _fetch_one(sql, params=()):
    conn = db_logging.get_connection(DB_TEST_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def _fetch_all(sql, params=()):
    conn = db_logging.get_connection(DB_TEST_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def test_normal_request_creates_one_row():
    answer = {"answer": "4", "model_used": "openai/gpt-5.6-luna", "input_tokens": 10,
              "output_tokens": 2, "cost": 0.00001, "llm_time_taken": 0.5, "error": None,
              "tools_used": None, "gate_log": None}
    db_logging.save_request("11111111-1111-1111-1111-111111111111", "What is 2+2?",
                             _decision(), _route_result(), answer, 0.9, db_name=DB_TEST_NAME)

    row = _fetch_one("SELECT message, route, model_used, cost FROM requests WHERE id = %s",
                      ("11111111-1111-1111-1111-111111111111",))
    assert row == ("What is 2+2?", "small_llm", "openai/gpt-5.6-luna", 0.00001)
    tool_calls = _fetch_all("SELECT * FROM tool_calls WHERE request_id = %s",
                             ("11111111-1111-1111-1111-111111111111",))
    assert tool_calls == []


def test_agent_request_with_2_tools_creates_1_request_row_and_2_tool_call_rows():
    answer = {
        "answer": "Done.", "model_used": "openai/gpt-5.6-luna", "input_tokens": None,
        "output_tokens": None, "cost": None, "llm_time_taken": 3.0, "error": None,
        "tools_used": [
            {"name": "search", "input": {"query": "a"}, "output": {"results": [], "error": None}},
            {"name": "calculator", "input": {"expression": "1+1"}, "output": {"result": 2, "error": None}},
        ],
        "gate_log": [
            {"tool": "search", "input": {"query": "a"}, "result": "ALLOW", "reason": "ok",
             "time_taken": 0.4, "destructive_score": 0.02, "matches_score": 0.9},
            {"tool": "calculator", "input": {"expression": "1+1"}, "result": "ALLOW", "reason": "ok",
             "time_taken": 0.3, "destructive_score": 0.01, "matches_score": 0.95},
        ],
    }
    db_logging.save_request("22222222-2222-2222-2222-222222222222", "search then add",
                             _decision(), _route_result(route="agent", rule=5, reason="needs_tool"),
                             answer, 1.2, db_name=DB_TEST_NAME)

    requests_count = _fetch_one("SELECT count(*) FROM requests WHERE id = %s",
                                 ("22222222-2222-2222-2222-222222222222",))
    assert requests_count == (1,)
    tool_calls = _fetch_all(
        "SELECT step_number, tool, executed FROM tool_calls WHERE request_id = %s ORDER BY step_number",
        ("22222222-2222-2222-2222-222222222222",),
    )
    assert tool_calls == [(1, "search", True), (2, "calculator", True)]


def test_blocked_tool_is_logged_with_executed_false():
    answer = {
        "answer": "I can't do that.", "model_used": "openai/gpt-5.6-luna", "input_tokens": None,
        "output_tokens": None, "cost": None, "llm_time_taken": 1.0, "error": None,
        "tools_used": [{"name": "delete_user", "input": {"user_id": 3},
                         "output": {"error": "needs_approval: tool 'delete_user' is marked destructive"}}],
        "gate_log": [{"tool": "delete_user", "input": {"user_id": 3}, "result": "NEEDS_APPROVAL",
                      "reason": "tool 'delete_user' is marked destructive", "time_taken": 0.4,
                      "destructive_score": 0.95, "matches_score": 0.9}],
    }
    db_logging.save_request("33333333-3333-3333-3333-333333333333", "delete user 3",
                             _decision(), _route_result(route="agent", rule=5, reason="needs_tool"),
                             answer, 1.0, db_name=DB_TEST_NAME)

    row = _fetch_one(
        "SELECT gate_result, executed FROM tool_calls WHERE request_id = %s",
        ("33333333-3333-3333-3333-333333333333",),
    )
    assert row == ("NEEDS_APPROVAL", False)


def test_database_down_does_not_raise_and_app_still_gets_an_answer(monkeypatch):
    def _refuse_connection(db_name=None):
        raise ConnectionError("simulated: database is down")
    monkeypatch.setattr(db_logging, "get_connection", _refuse_connection)

    answer = {"answer": "still works", "model_used": "openai/gpt-5.6-luna", "input_tokens": None,
              "output_tokens": None, "cost": None, "llm_time_taken": 0.5, "error": None,
              "tools_used": None, "gate_log": None}
    # Must not raise - this is the whole point of failing open.
    db_logging.save_request("44444444-4444-4444-4444-444444444444", "anything",
                             _decision(), _route_result(), answer, 0.5, db_name=DB_TEST_NAME)


def test_no_api_key_appears_anywhere_in_saved_data():
    answer = {"answer": "some answer mentioning nothing secret", "model_used": "openai/gpt-5.6-luna",
              "input_tokens": 5, "output_tokens": 5, "cost": 0.0001, "llm_time_taken": 0.5,
              "error": None, "tools_used": None, "gate_log": None}
    db_logging.save_request("55555555-5555-5555-5555-555555555555", "a normal message",
                             _decision(), _route_result(), answer, 0.5, db_name=DB_TEST_NAME)

    row = _fetch_one(
        "SELECT message, route, reason, model_used FROM requests WHERE id = %s",
        ("55555555-5555-5555-5555-555555555555",),
    )
    row_text = " ".join(str(v) for v in row)
    assert OPENROUTER_API_KEY not in row_text
    assert TAVILY_API_KEY not in row_text
