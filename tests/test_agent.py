"""Fake-LLM tests - no network, no API key. The fake LLM follows a script
of canned OpenRouter-shaped assistant messages, and check_gate() is faked
too (see test_gate.py for the gate's own rules), so these tests prove the
graph's wiring (propose -> execute -> loop / stop) without ever calling a
real model or a real Jev gate check."""
import itertools

from app.agents import agent
from app.safety.gate import GateResult
from app.tools import database


def _tool_call_msg(name, arguments, call_id="call_1"):
    return {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}],
    }


def _answer_msg(content):
    return {"role": "assistant", "content": content, "tool_calls": None}


def _scripted_llm(responses):
    it = iter(responses)
    calls = []

    def _fake(model, messages):
        calls.append(model)
        return next(it)

    _fake.calls = calls
    return _fake


def _fake_gate(result="ALLOW", reason="ok"):
    def _fake(tool_name, arguments, user_message, destructive_label):
        return GateResult(result=result, reason=reason, time_taken=0.01)
    return _fake


def test_calculator_tool_used_then_final_answer(monkeypatch):
    fake = _scripted_llm([
        _tool_call_msg("calculator", '{"expression": "847 * 23"}'),
        _answer_msg("The result is 19481."),
    ])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)
    monkeypatch.setattr(agent, "check_gate", _fake_gate("ALLOW"))

    result = agent.run_agent("What is 847 * 23?")

    assert "19481" in result["answer"]
    assert result["steps"] == 1
    assert result["tools_used"] == [
        {"name": "calculator", "input": {"expression": "847 * 23"}, "output": {"result": 19481, "error": None}}
    ]
    assert result["gate_log"] == [
        {
            "tool": "calculator", "input": {"expression": "847 * 23"}, "result": "ALLOW", "reason": "ok",
            "time_taken": 0.01, "destructive_score": None, "matches_score": None,
        }
    ]


def test_infinite_tool_requests_stop_at_max_steps(monkeypatch):
    fake = _scripted_llm(itertools.repeat(_tool_call_msg("calculator", '{"expression": "1 + 1"}')))
    monkeypatch.setattr(agent, "_call_agent_llm", fake)
    monkeypatch.setattr(agent, "check_gate", _fake_gate("ALLOW"))

    result = agent.run_agent("keep going forever")

    from app.config import AGENT_MAX_STEPS
    assert result["steps"] == AGENT_MAX_STEPS
    assert len(result["tools_used"]) == AGENT_MAX_STEPS
    assert "maximum" in result["answer"].lower()


def test_destructive_tool_needs_approval_and_user_still_exists(monkeypatch):
    database.reset()
    fake = _scripted_llm([
        _tool_call_msg("delete_user", '{"user_id": 3}'),
        _answer_msg("I can't delete that user without approval."),
    ])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)
    monkeypatch.setattr(
        agent, "check_gate",
        _fake_gate("NEEDS_APPROVAL", "tool 'delete_user' is marked destructive - never runs automatically"),
    )

    result = agent.run_agent("delete user 3")

    assert result["tools_used"][0]["output"]["error"].startswith("needs_approval:")
    assert database.read_user(3)["name"] == "Carla Reyes"
    database.reset()


def test_mismatched_tool_is_blocked(monkeypatch):
    # Prompt-injection shape: user asked to search, the agent (having read
    # a poisoned result, or just misbehaving) proposes delete_user instead.
    fake = _scripted_llm([
        _tool_call_msg("delete_user", '{"user_id": 3}'),
        _answer_msg("I won't do that - it doesn't match your request."),
    ])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)
    monkeypatch.setattr(agent, "check_gate", _fake_gate("BLOCK", "doesn't match the request (match score 0.02 < 0.5)"))

    database.reset()
    result = agent.run_agent("Search for info about our users")

    assert result["tools_used"][0]["output"]["error"].startswith("block:")
    assert database.read_user(3)["name"] == "Carla Reyes"


def test_no_tool_runs_without_passing_the_gate(monkeypatch):
    """The single most important guarantee: there is no shortcut path to a
    tool's func. Proven by making the gate always say BLOCK and the tool's
    own func explode if it's ever called - it never is."""
    def _explode(**kwargs):
        raise AssertionError("calculator.calculate() ran without gate approval")
    monkeypatch.setitem(agent.TOOLS_BY_NAME["calculator"], "func", _explode)
    monkeypatch.setattr(agent, "check_gate", _fake_gate("BLOCK", "doesn't match the request (match score 0.0 < 0.5)"))

    fake = _scripted_llm([
        _tool_call_msg("calculator", '{"expression": "1 + 1"}'),
        _answer_msg("blocked"),
    ])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)

    result = agent.run_agent("what is 1 + 1?")

    assert result["tools_used"][0]["output"]["error"].startswith("block:")


def test_tool_error_is_handled_and_agent_still_answers(monkeypatch):
    fake = _scripted_llm([
        _tool_call_msg("read_user", '{"user_id": 999}'),
        _answer_msg("That user doesn't exist."),
    ])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)
    monkeypatch.setattr(agent, "check_gate", _fake_gate("ALLOW"))

    result = agent.run_agent("read user 999")

    assert result["tools_used"][0]["output"] == {"error": "user 999 not found"}
    assert result["answer"] == "That user doesn't exist."


def test_think_trims_multiple_tool_calls_to_one(monkeypatch):
    # A model can return >1 tool_calls in one message even with
    # parallel_tool_calls=False requested (some providers ignore it). If
    # the stored history still declared the extra ones with no matching
    # tool response, the next real call would 400 - confirmed live
    # against the real OpenRouter API.
    multi_call_msg = {
        "role": "assistant", "content": None,
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"query": "a"}'}},
            {"id": "call_2", "type": "function", "function": {"name": "search", "arguments": '{"query": "b"}'}},
        ],
    }
    monkeypatch.setattr(agent, "_call_agent_llm", lambda model, messages: multi_call_msg)

    state = {
        "messages": [{"role": "user", "content": "search something"}],
        "model": "any", "proposed_tool": None, "tools_used": [], "step_count": 0, "final_answer": None,
    }
    update = agent.think(state)

    assert update["proposed_tool"] == {"id": "call_1", "name": "search", "arguments": {"query": "a"}}
    stored_msg = update["messages"][-1]
    assert len(stored_msg["tool_calls"]) == 1
    assert stored_msg["tool_calls"][0]["id"] == "call_1"


def test_direct_answer_with_no_tool_call(monkeypatch):
    fake = _scripted_llm([_answer_msg("Hi there!")])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)

    result = agent.run_agent("hello")

    assert result["answer"] == "Hi there!"
    assert result["tools_used"] == []
    assert result["steps"] == 0


def test_complexity_label_picks_the_model(monkeypatch):
    from app.config import SMALL_LLM_MODEL, STRONG_LLM_MODEL

    fake = _scripted_llm([_answer_msg("ok"), _answer_msg("ok"), _answer_msg("ok")])
    monkeypatch.setattr(agent, "_call_agent_llm", fake)

    agent.run_agent("simple one", complexity_label="simple")
    agent.run_agent("in-between one", complexity_label="moderate")
    agent.run_agent("hard one", complexity_label="complex")

    # Only "complex" should reach for the expensive model - same boundary
    # the router itself uses. Caught live: "847 * 23" and "latest SpaceX
    # news" both scored "moderate" and were wrongly sent to Terra before
    # this test existed, because "moderate" wasn't exercised here.
    assert fake.calls == [SMALL_LLM_MODEL, SMALL_LLM_MODEL, STRONG_LLM_MODEL]
