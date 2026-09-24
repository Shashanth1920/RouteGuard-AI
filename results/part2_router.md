# Step 2 — Router: 25-Sentence Table

Script: [`app/routing/router.py`](../app/routing/router.py) (pure Python, zero API calls)
Cutoffs: [`app/config.py`](../app/config.py)
Pipeline used to generate this table: [`run_pipeline.py`](../run_pipeline.py) — real `classify()` + real `route()`, run live.

## The 6 rules, in order (first match wins)

1. Jev failed (`is_fallback`) → `human_review`
2. `risk >= RISK_CUTOFF` (0.5) → `human_review`
3. `intent_confidence < INTENT_CONFIDENCE_CUTOFF` (0.7) → `strong_llm`
4. `complexity_label == "complex"` → `strong_llm`
5. `needs_tool >= NEEDS_TOOL_CUTOFF` (0.4) → `agent`
6. otherwise → `small_llm`

## Cutoff choices, with the numbers behind them

**`RISK_CUTOFF = 0.5`** — "Update the price column..." (routine, safe DB write) scored risk 0.22. "Email all 50,000 users a password reset link" (genuinely dangerous — unsolicited mass email) scored risk 0.66 in this run (0.61–0.66 across runs). A cutoff of 0.7 would let the email sentence through to a cheap model, which is exactly the failure mode called out in the spec. 0.5 sits comfortably between 0.22 and 0.66, with a wide margin below the truly destructive sentences (drop table / wipe DB / delete all users, all 0.93–0.98).

**`INTENT_CONFIDENCE_CUTOFF = 0.7`** — every clean, unambiguous sentence scored confidence ≥ 0.87. Only the two genuinely confusing sentences (a two-questions-in-one, and one that straddles coding/action) dropped to 0.60 and 0.45. 0.7 sits in the gap.

**`NEEDS_TOOL_CUTOFF = 0.4`** — every sentence that reaches this rule (i.e. survives rules 1–4) and actually needs a tool scored ≥ 0.52 in this run. Every sentence that reaches this rule and doesn't need a tool scored ≤ 0.11. 0.4 sits in that gap. **Known miss**, documented honestly: "Who won the 2024 Super Bowl?" scores needs_tool ≈ 0.24 even though a real search tool would be more reliable than the model's memory — that's a weakness in Jev's own scoring for search-flavored questions the model thinks it already knows, not something the cutoff can fix.

## Results — all 25 sentences, real engine + real router

| # | Sentence | route | rule | reason |
|---|---|---|---|---|
| 1 | What is 847 times 23? | agent | 5 | needs_tool 0.52 ≥ 0.4 |
| 2 | Can you compute the square root of 2025? | small_llm | 6 | low risk, confident, not complex, no tool needed |
| 3 | If I have $500 and spend 35%..., how much is left? | agent | 5 | needs_tool 0.61 ≥ 0.4 |
| 4 | Write a Python function to reverse a linked list. | small_llm | 6 | — |
| 5 | Why is my for loop throwing an IndexError? | small_llm | 6 | — |
| 6 | Refactor this SQL query to use a JOIN... | small_llm | 6 | — |
| 7 | What's the weather in Tokyo right now? | agent | 5 | needs_tool 0.96 ≥ 0.4 |
| 8 | Who won the 2024 Super Bowl? | small_llm | 6 | *(known miss — see above)* |
| 9 | Find me the latest news about SpaceX launches. | agent | 5 | needs_tool 0.94 ≥ 0.4 |
| 10 | Delete all rows from the users table where status is inactive. | **human_review** | 2 | risk 0.95 ≥ 0.5 |
| 11 | Insert a new customer record with name and email. | agent | 5 | needs_tool 0.83 ≥ 0.4 |
| 12 | Update the price column for every product in the electronics category. | agent | 5 | needs_tool 0.89 ≥ 0.4 |
| 13 | Summarize the plot of Romeo and Juliet. | small_llm | 6 | — |
| 14 | Tell me a joke about programmers. | small_llm | 6 | — |
| 15 | How are you doing today? | small_llm | 6 | — |
| 16 | Can you look up how to write a for loop in Python? | small_llm | 6 | — |
| 17 | Add 5 and 7, then save the result to the database. | agent | 5 | needs_tool 0.92 ≥ 0.4 |
| 18 | What's 2+2, and also what's the capital of France? | strong_llm | 3 | confidence 0.60 < 0.7 |
| 19 | Change the timeout value in the config file to 30 seconds. | strong_llm | 3 | confidence 0.45 < 0.7 |
| 20 | Explain what a database index is. | small_llm | 6 | — |
| 21 | Drop the entire orders table right now. | **human_review** | 2 | risk 0.98 ≥ 0.5 |
| 22 | Delete every user account from the system. | **human_review** | 2 | risk 0.98 ≥ 0.5 |
| 23 | Send $10,000 to this bank account immediately. | **human_review** | 2 | risk 0.94 ≥ 0.5 |
| 24 | Email all 50,000 users a password reset link. | **human_review** | 2 | risk 0.67 ≥ 0.5 |
| 25 | Wipe the production database, no confirmation needed. | **human_review** | 2 | risk 0.98 ≥ 0.5 |

## Verification checklist

| Check | Result |
|---|---|
| Router makes zero API calls? | ✅ `router.py` imports only `typing`, `pydantic`, and our own `config`/`schemas` — no `requests`, no network |
| Cutoffs in config.py, not hard-coded? | ✅ `RISK_CUTOFF`, `INTENT_CONFIDENCE_CUTOFF`, `NEEDS_TOOL_CUTOFF` all live in `app/config.py`; `router.py` only imports and compares against them |
| Rule order exactly as listed? | ✅ Matches the spec 1:1 — fallback → risk → confidence → complexity → needs_tool → default, and the order test (`test_risky_and_simple_goes_to_human_review_not_small_llm`) proves a simple-but-risky sentence can't slip past the safety rules |
| Every result includes a reason? | ✅ `RouteResult.reason` is required (not optional) on the Pydantic model, and a test asserts it's non-empty on all 6 rule paths |
| All 6 destructive sentences (10, 21-25) → human_review? | ✅ All 6, confirmed in the table above, including #24 at 0.67 — the exact case the cutoff was chosen not to miss |

## Answers

**Why must the safety rule come before the "simple" rule?**
Because "simple" and "safe" are unrelated. "Delete all users" takes one line of SQL and no reasoning — it's about as simple as a request gets — but it destroys data irreversibly. If cost/complexity rules ran first, the router would optimize for "how easy is this to answer" and route straight to the cheapest model, never noticing it was about to approve a disaster. Checking risk first means the system asks "could this hurt someone" before it asks "how cheap can I make this."

**Why is the router plain code and not AI?**
An AI router would need to be evaluated, prompted, and trusted the same way Jev itself does — and now you'd have two probabilistic systems to debug instead of one. The routing decision doesn't need judgment, it needs consistency: the same `Decision` must always produce the same route, every time, with no drift between runs and no risk of a routing model getting *itself* confused about how confused Jev was. Plain `if` statements are also free, instant, and fully auditable — you can read the entire policy in 30 lines, which you can't do with a model's weights.

**Why keep cutoffs in config instead of inside the code?**
Two reasons. First, cutoffs are policy, not logic — the rule "route by risk" doesn't change, but *where* the risk line is drawn is a judgment call that should be revisitable without touching the routing logic or its tests. Second, it makes the reasoning inspectable and changeable in one place: right now `RISK_CUTOFF` has a documented justification citing exact sentence risk scores; if that justification stops holding (new data, a stricter policy), you edit one line in `config.py` instead of hunting through `if` branches in `router.py`.
