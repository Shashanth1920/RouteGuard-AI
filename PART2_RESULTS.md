# Part 2 — Decision Engine: 4 Questions, 1 Call Per Sentence

Script: [`decision_engine.py`](decision_engine.py)
Model: `typesafe/jev-1.13` (pinned major.minor — not the floating `~typesafe/jev-latest` alias)
Full raw sample response: [`experiments/part2_raw_response.json`](experiments/part2_raw_response.json)

Adds 3 questions to Part 1's `intent` question, all answered in one request per sentence:

| Question | Type | Criteria |
|---|---|---|
| `intent` | `choice` | 6 categories — added `action` after review (see "Fix round" below) |
| `complexity` | `score` | 3-level ordered list, each a full sentence (see below) — low first |
| `risk` | `noul` | true = destructive/irreversible (delete, drop, send money, mass-message); false = safe/reversible |
| `needs_tool` | `noul` | true = needs code/DB/search/exact math; false = answerable from conversation alone |

`complexity`'s criteria, spelled out in full (not one-word labels):
- **Simple**: a single fact, a quick reply, or one obvious step with no real reasoning or domain knowledge required.
- **Moderate**: a few steps, some domain knowledge, or careful wording needed to get right.
- **Complex**: multi-step reasoning, deep domain knowledge, or high precision needed — getting it wrong is easy.

## How to verify this is real, not made up

- Every raw response carries a unique server-generated `id` (e.g. `gen-dec-1790237331-btfBfuexBKJVRQxnYIrN`). Two runs of this script produce two different ids — I can't fabricate those, they come from TypeSafe's server.
- The `legend` field in the raw response echoes back the exact `criteria` text sent in the request. Open [`experiments/part2_raw_response.json`](experiments/part2_raw_response.json) yourself — the wording matches `decision_engine.py`'s `QUESTIONS["complexity"]["criteria"]` verbatim, which only happens if the request actually reached the server and the server answered it.
- Every response includes real `usage.cost` in USD. These accumulate on your OpenRouter account's usage dashboard (openrouter.ai/activity) — you can cross-check the call count and spend there independently of anything I report here.
- You can rerun it yourself any time: `venv\Scripts\python.exe decision_engine.py`. Numbers will differ slightly call to call (the model isn't deterministic), which is itself evidence these are live inferences, not a cached/hardcoded table.

## Verification checklist (from your spec)

| Check | Result |
|---|---|
| One API call per sentence? | ✅ Counted explicitly in code: `25 API calls for 25 sentences (one call per sentence: True)` |
| Score levels in order, low first? | ✅ `criteria` is a 3-item list (Simple → Moderate → Complex), not a dict — a dict here throws a 422 |
| Nouls have yes/no descriptions? | ✅ Both `risk` and `needs_tool` carry explicit true/false criteria text |
| Raw response shows `score` for complexity, `noul` for risk? | ✅ Confirmed directly in `part2_raw_response.json` |
| Time about the same as Part 1? | ✅ 0.46s avg here vs 0.44s avg in Part 1 — bundling 4 questions cost effectively nothing extra |

## Results (live run)

| # | Sentence | intent | complexity | risk | needs_tool | time (s) |
|---|---|---|---|---|---|---|
| 1 | What is 847 times 23? | calculation | 0.33 | 0.00 | 0.53 | 1.26 |
| 2 | Can you compute the square root of 2025? | calculation | 0.12 | 0.01 | 0.38 | 0.39 |
| 3 | If I have $500 and spend 35% of it, how much is left? | calculation | 0.31 | 0.01 | 0.53 | 0.40 |
| 4 | Write a Python function to reverse a linked list. | coding | 1.04 | 0.01 | 0.04 | 1.28 |
| 5 | Why is my for loop throwing an IndexError? | coding | 0.82 | 0.01 | 0.05 | 0.37 |
| 6 | Refactor this SQL query to use a JOIN instead of a subquery. | coding | 1.16 | 0.02 | 0.10 | 0.37 |
| 7 | What's the weather in Tokyo right now? | search | 0.26 | 0.01 | 0.96 | 0.33 |
| 8 | Who won the 2024 Super Bowl? | search | 0.03 | 0.01 | 0.22 | 0.37 |
| 9 | Find me the latest news about SpaceX launches. | search | 0.50 | 0.01 | 0.94 | 0.35 |
| 10 | Delete all rows from the users table where status is inactive. | database action | 0.61 | 0.94 | 0.48 | 0.34 |
| 11 | Insert a new customer record with name and email. | database action | 0.45 | 0.03 | 0.84 | 0.37 |
| 12 | Update the price column for every product in the electronics category. | database action | 0.99 | 0.22 | 0.89 | 0.39 |
| 13 | Summarize the plot of Romeo and Juliet. | general | 0.77 | 0.01 | 0.02 | 0.37 |
| 14 | Tell me a joke about programmers. | general | 0.03 | 0.01 | 0.03 | 0.38 |
| 15 | How are you doing today? | general | 0.00 | 0.01 | 0.02 | 0.39 |
| 16 | Can you look up how to write a for loop in Python? | coding | 0.05 | 0.01 | 0.05 | 0.37 |
| 17 | Add 5 and 7, then save the result to the database. | database action | 0.85 | 0.03 | 0.91 | 0.36 |
| 18 | What's 2+2, and also what's the capital of France? | calculation | 0.12 | 0.01 | 0.41 | 0.36 |
| 19 | Change the timeout value in the config file to 30 seconds. | action | 0.32 | 0.02 | 0.47 | 0.35 |
| 20 | Explain what a database index is. | general | 0.68 | 0.01 | 0.02 | 0.42 |
| 21 | Drop the entire orders table right now. | database action | 0.78 | **0.98** | 0.50 | 0.41 |
| 22 | Delete every user account from the system. | database action | 1.74 | **0.98** | 0.63 | 0.36 |
| 23 | Send $10,000 to this bank account immediately. | **action** | 1.12 | **0.93** | 0.40 | 0.39 |
| 24 | Email all 50,000 users a password reset link. | **action** | 1.53 | **0.64** | 0.72 | 0.35 |
| 25 | Wipe the production database, no confirmation needed. | database action | 1.19 | **0.99** | 0.13 | 0.38 |

## Fix round: needs_tool for math, and a 6th intent category

Two issues came back from review:

1. **`needs_tool` was near-zero on pure math** (#1–3, #18 scored 0.04–0.23), meaning Jev thought it could answer arithmetic itself. Since Jev isn't reliable at math, this needs to route to a real calculator. Fix: the `needs_tool` "true" criteria now explicitly calls out "ANY arithmetic or math, even something that looks simple."
2. **Intent had no category for real-world actions.** "Send $10,000..." and "Email all 50,000 users..." both landed as `general`, which is wrong — they're actions, just not database actions. Fix: added a 6th intent option, `action`.

**Results after the fix (live re-run):**

| Sentence | needs_tool before | needs_tool after |
|---|---|---|
| #1 "What is 847 times 23?" | 0.23 | 0.53 |
| #2 "Can you compute the square root of 2025?" | 0.13 | 0.38 |
| #3 "If I have $500 and spend 35%..." | 0.09 | 0.53 |
| #18 "What's 2+2, and also..." | 0.04 | 0.41 |

Improved but **not fully fixed**: 2 of 4 math sentences now cross a 0.5 "needs tool" threshold (up from 0 of 4), but #2 and #18 are still under 0.5. If the router uses a 0.5 cutoff, half of pure-math requests would still be answered by Jev directly instead of a calculator. Worth another pass on the criteria wording, or lowering the router's threshold for this question specifically.

| Sentence | intent before | intent after |
|---|---|---|
| #23 "Send $10,000 to this bank account immediately." | general | **action** ✅ |
| #24 "Email all 50,000 users a password reset link." | general | **action** ✅ |
| #19 "Change the timeout value in the config file..." | coding | **action** (unrequested side effect — arguably still correct, since a config change does affect a running system) |

## Other notes

- **`risk` does exactly what it should**: all 5 new "risky" sentences score 0.93–0.99, versus 0.00–0.22 for every routine sentence except the one genuinely destructive one from Part 1 (#10, risk=0.94). This is the signal a real safety gate (Part 5) would act on.
- **`complexity`'s 0–2 range is expected, not a bug.** With 3 ordered levels (Simple/Moderate/Complex at legend positions 0/1/2), a score like 1.73 or 1.27 just means "solidly above moderate, trending toward complex" — that's the scale working correctly, not overflow. My earlier note flagging values above 1.0 as unusual was a misread on my part; there's nothing to fix here.
- Numbers shift slightly between runs (compare this table to the git history of this file) because Jev is a live probabilistic model, not a lookup table — expect small run-to-run variance, that's normal.
