"""The doctor that uses the equipment. Built by hand with LangGraph's
StateGraph (not the prebuilt create_react_agent) because "propose tool" and
"execute tool" must be 2 separate steps - Part 5's Safety Gate goes right
between them, like a nurse checking a prescription before the medicine is
given. Building it now with 2 steps means Part 5 doesn't require rebuilding
the graph, only replacing what execute_tool does with the proposal.

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
    proposed_tool: Optional[dict]
    tools_used: list
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
        },
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def think(state: AgentState) -> dict:
    assistant_msg = _call_agent_llm(state["model"], state["messages"])
    messages = state["messages"] + [assistant_msg]

    tool_calls = assistant_msg.get("tool_calls")
    if not tool_calls:
        return {"messages": messages, "final_answer": assistant_msg.get("content") or "", "proposed_tool": None}

    call = tool_calls[0]
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
    proposal = state["proposed_tool"]
    name, arguments = proposal["name"], proposal["arguments"]
    entry = TOOLS_BY_NAME.get(name)

    if entry is None:
        output = {"error": f"unknown tool '{name}'"}
    elif entry["destructive"]:
        # Temporary lock until Part 5 replaces this with the real Jev
        # Safety Gate. No destructive tool runs without it.
        output = {"error": "blocked: needs approval"}
    else:
        try:
            output = entry["func"](**arguments)
        except Exception as e:
            output = {"error": str(e)}

    tool_message = {"role": "tool", "tool_call_id": proposal["id"], "content": json.dumps(output)}
    return {
        "messages": state["messages"] + [tool_message],
        "tools_used": state["tools_used"] + [{"name": name, "input": arguments, "output": output}],
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
    # Reuse Jev's complexity score: Luna thinks for simple tasks, Terra for
    # anything moderate/complex - same "don't pay specialist prices for
    # junior-doctor work" logic as the router's own model choice.
    model = SMALL_LLM_MODEL if complexity_label == "simple" else STRONG_LLM_MODEL
    start = time.time()
    initial_state: AgentState = {
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "model": model,
        "proposed_tool": None,
        "tools_used": [],
        "step_count": 0,
        "final_answer": None,
    }
    result = _GRAPH.invoke(initial_state)
    return {
        "answer": result["final_answer"],
        "model_used": model,
        "tools_used": result["tools_used"],
        "steps": result["step_count"],
        "agent_time_taken": time.time() - start,
    }
