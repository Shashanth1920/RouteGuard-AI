"""The doctor that uses the equipment. Built by hand with LangGraph's
StateGraph (not the prebuilt create_react_agent) because "propose tool" and
"execute tool" are 2 separate steps - the Safety Gate (app/safety/gate.py)
runs inside execute_tool, right before any tool's func is actually called,
like a pharmacist checking a prescription before the medicine is given.

Flow: think -> (wants a tool?) -> propose_tool -> execute_tool -> think
                (ready?)        -> answer -> end
"""
import json
import time
from typing import Optional, TypedDict

import requests
from langgraph.graph import END, START, StateGraph

from app.config import (
    AGENT_MAX_STEPS,
    AGENT_SYSTEM_PROMPT,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT,
    OPENROUTER_API_KEY,
    SMALL_LLM_MODEL,
    STRONG_LLM_MODEL,
)
from app.safety.gate import check_gate
from app.tools.registry import TOOLS

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SESSION = requests.Session()

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {"name": t["name"], "description": t["description"], "parameters": t["params"]},
    }
    for t in TOOLS
]


class AgentState(TypedDict):
    messages: list
    model: str
    user_message: str
    proposed_tool: Optional[dict]
    tools_used: list
    gate_log: list
    step_count: int
    final_answer: Optional[str]


def _call_agent_llm(model: str, messages: list) -> dict:
    """One call to the model doing the thinking. A module-level function
    (not inlined in think()) so tests can swap it for a scripted fake LLM."""
    resp = SESSION.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={
            "model": model,
            "max_tokens": LLM_MAX_TOKENS,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
            # The graph only ever proposes/executes 1 tool per step (on
            # purpose - Part 5's Safety Gate checks one proposal at a time).
            # Without this, the model sometimes returns several tool_calls
            # in one turn; execute_tool only answers the first, leaving the
            # rest dangling - confirmed live, OpenRouter's next call then
            # 400s with an unhandled HTTPError and no response body.
            "parallel_tool_calls": False,
        },
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def think(state: AgentState) -> dict:
    assistant_msg = _call_agent_llm(state["model"], state["messages"])

    tool_calls = assistant_msg.get("tool_calls")
    if not tool_calls:
        messages = state["messages"] + [assistant_msg]
        return {"messages": messages, "final_answer": assistant_msg.get("content") or "", "proposed_tool": None}

    # We only ever execute 1 tool per step. Trim the stored message to
    # match, even though parallel_tool_calls=False should already prevent
    # more than one - a provider that ignores that flag must never leave
    # a tool_call in history with no matching tool response, or the next
    # call 400s (confirmed live: this is exactly what happened before
    # parallel_tool_calls was added).
    call = tool_calls[0]
    assistant_msg = {**assistant_msg, "tool_calls": [call]}
    messages = state["messages"] + [assistant_msg]
    try:
        arguments = json.loads(call["function"]["arguments"] or "{}")
    except (json.JSONDecodeError, TypeError):
        arguments = {}
    return {
        "messages": messages,
        "proposed_tool": {"id": call["id"], "name": call["function"]["name"], "arguments": arguments},
    }


def propose_tool(state: AgentState) -> dict:
    """Deliberately its own step, doing nothing today, so Part 5's Safety
    Gate has a place to intercept between "the agent wants to do X" and
    "X actually happens" without changing the graph's shape."""
    return {}


def execute_tool(state: AgentState) -> dict:
    """The only place any tool's func actually runs. Every proposal goes
    through check_gate() first - there is no other path to entry["func"]."""
    proposal = state["proposed_tool"]
    name, arguments = proposal["name"], proposal["arguments"]
    entry = TOOLS_BY_NAME.get(name)

    if entry is None:
        output = {"error": f"unknown tool '{name}'"}
        gate_entry = {"tool": name, "input": arguments, "result": "BLOCK", "reason": "unknown tool", "time_taken": 0.0}
    else:
        gate = check_gate(name, arguments, state["user_message"], entry["destructive"])
        gate_entry = {
            "tool": name, "input": arguments, "result": gate.result,
            "reason": gate.reason, "time_taken": gate.time_taken,
        }
        if gate.result == "ALLOW":
            try:
                output = entry["func"](**arguments)
            except Exception as e:
                output = {"error": str(e)}
        else:
            output = {"error": f"{gate.result.lower()}: {gate.reason}"}

    tool_message = {"role": "tool", "tool_call_id": proposal["id"], "content": json.dumps(output)}
    return {
        "messages": state["messages"] + [tool_message],
        "tools_used": state["tools_used"] + [{"name": name, "input": arguments, "output": output}],
        "gate_log": state["gate_log"] + [gate_entry],
        "step_count": state["step_count"] + 1,
        "proposed_tool": None,
    }


def answer(state: AgentState) -> dict:
    if state.get("final_answer"):
        return {}
    return {"final_answer": f"Reached the maximum of {AGENT_MAX_STEPS} steps without a final answer."}


def _after_think(state: AgentState) -> str:
    return "propose_tool" if state["proposed_tool"] else "answer"


def _after_execute(state: AgentState) -> str:
    return "answer" if state["step_count"] >= AGENT_MAX_STEPS else "think"


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("think", think)
    graph.add_node("propose_tool", propose_tool)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("answer", answer)
    graph.add_edge(START, "think")
    graph.add_conditional_edges("think", _after_think)
    graph.add_edge("propose_tool", "execute_tool")
    graph.add_conditional_edges("execute_tool", _after_execute)
    graph.add_edge("answer", END)
    return graph.compile()


_GRAPH = _build_graph()


def run_agent(message: str, complexity_label: str = "simple") -> dict:
    # Reuse Jev's complexity score, same boundary the router itself uses
    # (Part 3 rule 4: only "complex" escalates) - "moderate" stays on Luna,
    # not Terra. A tighter boundary (only "simple" -> Luna) looked right at
    # first but sent ordinary requests like "847 * 23" and "latest SpaceX
    # news" (both scored "moderate") to Terra for no real benefit - caught
    # live, not by a test, since the fake-LLM tests never exercised the
    # "moderate" label.
    model = STRONG_LLM_MODEL if complexity_label == "complex" else SMALL_LLM_MODEL
    start = time.time()
    initial_state: AgentState = {
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "model": model,
        "user_message": message,
        "proposed_tool": None,
        "tools_used": [],
        "gate_log": [],
        "step_count": 0,
        "final_answer": None,
    }
    result = _GRAPH.invoke(initial_state)
    return {
        "answer": result["final_answer"],
        "model_used": model,
        "tools_used": result["tools_used"],
        "gate_log": result["gate_log"],
        "steps": result["step_count"],
        "agent_time_taken": time.time() - start,
    }
