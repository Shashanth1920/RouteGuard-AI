# Part 3 Step 2 — Wiring Up the 2 LLMs

Models: [`app/llm/client.py`](../app/llm/client.py) (`call_llm` + `get_answer`), pinned in
[`app/config.py`](../app/config.py) — `SMALL_LLM_MODEL = openai/gpt-5.6-luna`,
`STRONG_LLM_MODEL = openai/gpt-5.6-terra` (confirmed live on OpenRouter's model
list; terra prices ~10x luna per token, matching "cheap junior doctor" vs.
"expensive specialist").

## What each route does now

| Route | Behavior |
|---|---|
| `small_llm` | Calls `openai/gpt-5.6-luna` |
| `strong_llm` | Calls `openai/gpt-5.6-terra` |
| `agent` | No LLM call — returns `error: "agent not built yet"` |
| `human_review` | No LLM call — returns `error: "waiting for human approval"` |

Backup rule: if the small model call fails, `get_answer()` retries once on
the strong model. If the strong model fails (whether called directly or as
the backup), it returns a clean error — never a crash, never a silent retry
loop.

## Live verification — all 3 example types, real server, real calls

**"Tell me a joke"** → `small_llm`, answered by `openai/gpt-5.6-luna`
("Why did the scarecrow win an award? Because he was outstanding in his
field!"), cost $0.000029, LLM time 2.40s (Jev time 1.18s, kept separate).

**"Delete all users"** → `human_review`, risk 0.97 ≥ 0.5. `answer: null`,
`model_used: null`, `error: "waiting for human approval"` — confirmed **zero**
LLM call happened (no cost, no tokens, no llm_time_taken in the response).

**"Explain the risks in a 200-page financial report in 2 sentences"** →
routed to `small_llm`, not `strong_llm`. Honest result, not the one the spec
example expects: Jev scored this `complexity_score = 1.44`, which rounds to
label `"moderate"` (index 1 of 0/1/2), not `"complex"` — so rule 4 never
fires. This is the same complexity-scoring softness flagged in
[part2_router.md](part2_router.md); it isn't hidden here, and it's a
candidate for Part 7's larger evaluation set to check whether the complexity
wording or the round-to-label cutoff needs adjusting.

## Cost comparison — same question, both models

Question: *"Explain the main risks a company faces when reporting quarterly
earnings."* Called directly via `call_llm()`, bypassing the router, so both
models answer the identical prompt.

| Model | Time | Cost | Input / output tokens |
|---|---|---|---|
| `openai/gpt-5.6-luna` (small) | 4.55s | $0.0003498 | 27 / 287 |
| `openai/gpt-5.6-terra` (strong) | 7.29s | $0.004854 | 27 / 400 |

Terra cost **~13.9x** more than luna for this question and took 1.6x longer,
for a longer but not dramatically better answer on a question neither model
needed deep reasoning for — exactly the case for routing most traffic to the
cheap model and reserving the strong one for genuinely hard requests.

## Tests (`tests/test_llm.py`, no network, no API key)

| Test | Proves |
|---|---|
| `test_small_llm_route_calls_the_cheap_model` | `small_llm` → luna only |
| `test_strong_llm_route_calls_the_strong_model` | `strong_llm` → terra only |
| `test_human_review_never_calls_an_llm` | **zero calls**, `error` set |
| `test_agent_route_never_calls_an_llm` | zero calls, `error` set |
| `test_small_llm_failure_backs_up_to_strong_llm` | luna fails → terra called next, succeeds |
| `test_both_models_failing_returns_clean_error` | no crash, `error: "LLM call failed"` |
| `test_strong_llm_failure_has_no_backup` | terra fails → error, no retry loop |

35/35 tests pass (`venv\Scripts\python.exe -m pytest tests/ -v`).

## Answers

**Why must `human_review` never call an LLM?**
Because the whole point of that route is that a *person* decides, not a
model — calling an LLM anyway (even just to "help") would mean the system
quietly took an action on a request it just flagged as too risky to act on
without a human, defeating the entire safety gate.

**Why keep Jev time and LLM time separate?**
They measure different things and get optimized differently. Jev time is
the fixed cost of *deciding where to send a message* (one small API call);
LLM time is the cost of *actually answering it* and varies hugely by model
and route. Merging them would hide which part of the latency budget is the
decision overhead vs. the answer itself — exactly what the README cost/time
comparison needs to stay honest.

**Why use 2 models instead of always using the strong one?**
Cost and speed, proven above: terra cost ~14x more than luna for a question
neither model needed extra reasoning power for. Always calling the strong
model would mean paying specialist prices for junior-doctor work on every
easy request — the whole reason the router exists is to avoid exactly that.
