# Part 4 Step 2 — LangGraph Agent

Graph: [`app/agents/agent.py`](../app/agents/agent.py), built by hand with
`langgraph.graph.StateGraph` (not the prebuilt `create_react_agent`) — the
spec requires `propose_tool` and `execute_tool` as 2 separate steps so
Part 5's Safety Gate can intercept between them later without a rebuild.

## The graph

```
START -> think -> (wants a tool?) -> propose_tool -> execute_tool -> think (loop)
                -> (ready?)       -> answer -> END
```

`step_count` increments once per `execute_tool` call; once it reaches
`AGENT_MAX_STEPS` (5, in `app/config.py`), the loop is forced to `answer`
regardless of what the model still wants to do.

`execute_tool` currently refuses any tool marked `destructive` in the
registry (`delete_user`) and returns `{"error": "blocked: needs approval"}`
without running it — a temporary hardcoded lock. Part 5 replaces this with
the real Jev Safety Gate; the graph shape doesn't change, only what
`execute_tool` does with a destructive proposal.

Model choice reuses Jev's own `complexity_label`: `simple` → `openai/gpt-5.6-luna`,
anything else → `openai/gpt-5.6-terra` — same reasoning as the router's own
model choice in Part 3 (don't pay specialist prices for junior-doctor work).

## Live verification — real models, real tools, real server

**"What is 847 times 23? Use a tool."** → routed to `agent`, calculator
called with `{"expression": "847 * 23"}`, answer `"847 × 23 = **19,481**"`,
1 step.

**"What is the current weather in Tokyo right now?"** → routed to `agent`,
`search` called via real Tavily, 3 real results (including one page whose
content looked like an odds-market listing — irrelevant noise, not
followed as an instruction, exactly the prompt-injection defense point),
answer correctly summarized the actual weather.

**"List all users in the database"** → an honest miss, not hidden:
`intent_confidence` came back 0.68, just under the router's 0.7 cutoff, so
this landed on `strong_llm`, not `agent` — the strong model has no tool
access and just guessed a plausible `SELECT * FROM users` query instead of
listing anyone. Rephrased to **"Use the database tool to list every
user."** → `intent_confidence` 0.74, correctly routed to `agent`,
`list_users` called for real, all 10 fake users listed by name and email.
This is the same kind of Jev-confidence sensitivity already flagged in
Parts 2–3, not a bug in the agent or the tool itself.

**Direct agent call, bypassing the router entirely** — `run_agent("delete
user 3")`: the model proposed `delete_user({"user_id": 3})`, `execute_tool`
blocked it (`{"error": "blocked: needs approval"}`), and the agent answered
"Deletion of user 3 was blocked because approval is required." `read_user(3)`
confirmed Carla Reyes is still in the fake database afterward.

**Through the full API**, the same request ("Delete user 3") never reaches
the agent at all — Jev scored it risk 0.88 ≥ 0.5, router rule 2 fires,
`human_review`, zero LLM/agent calls. This is the first guard working, from
Part 2's router, before the agent's own destructive-tool lock is ever
needed as a second layer.

## Tests (`tests/test_agent.py`, scripted fake LLM, no network, no API key)

| Test | Proves |
|---|---|
| `test_calculator_tool_used_then_final_answer` | tool call → real calculator result → final answer includes 19481 |
| `test_infinite_tool_requests_stop_at_max_steps` | a fake LLM that always asks for a tool still stops at `AGENT_MAX_STEPS` (5), with a non-crashing final answer |
| `test_destructive_tool_is_blocked_and_user_still_exists` | `delete_user` proposal → blocked, fake DB unchanged |
| `test_tool_error_is_handled_and_agent_still_answers` | a tool returning `{"error": ...}` (unknown user) doesn't stop the agent from producing a final answer |
| `test_direct_answer_with_no_tool_call` | a fake LLM that never asks for a tool still works |
| `test_complexity_label_picks_the_model` | `simple` → luna, `complex` → terra |

Plus `test_llm.py::test_agent_route_delegates_to_run_agent_not_call_llm`,
proving `get_answer("agent", ...)` hands off to `run_agent()` and never
touches the plain `call_llm()` path.

52/52 tests pass total (`venv\Scripts\python.exe -m pytest tests/ -v`).

## Answers

**Why keep propose and execute as separate steps?**
Because the moment worth intercepting isn't "the agent decided to use a
tool" (that's still just an intention) — it's "the tool is about to
actually run." Keeping them as one step would mean any future safety check
either has to happen *inside* the tool's own execution code (scattering the
policy across every tool) or not at all. Two steps means Part 5's gate is
one clean node in between, reading the same `proposed_tool` the graph
already builds.

**Why do we need a max step limit?**
Every loop iteration is a real, paid model call. A model that gets stuck
proposing tools (bad arguments, a tool that keeps erroring, a confusing
task) would otherwise spin forever, and every spin costs money and time
with nothing to show for it. `AGENT_MAX_STEPS` guarantees the loop always
terminates and always returns *something*, even when the model can't
finish cleanly on its own — proven directly by
`test_infinite_tool_requests_stop_at_max_steps`.

**What is "state" in LangGraph, in your own words?**
It's the one dictionary that travels through every node in the graph, and
each node only returns the *changes* it wants to make to it (LangGraph
merges them in). Here that's the growing message history, which tools were
used and what they returned, how many steps have run, and the final
answer once there is one — the "patient's file" that every step of the
checklist reads from and writes back to, so no node needs to know how any
other node works internally.
