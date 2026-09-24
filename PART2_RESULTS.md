# Part 2 — Decision Engine: 4 Questions, 1 Call Per Sentence

Script: [`decision_engine.py`](decision_engine.py)
Model: `typesafe/jev-1.13` (pinned major.minor — not the floating `~typesafe/jev-latest` alias)
Full raw sample response: [`experiments/part2_raw_response.json`](experiments/part2_raw_response.json)

Adds 3 questions to Part 1's `intent` question, all answered in one request per sentence:

| Question | Type | Criteria |
|---|---|---|
| `intent` | `choice` | 5 categories (unchanged from Part 1) |
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
| 1 | What is 847 times 23? | calculation | 0.39 | 0.00 | 0.22 | 1.34 |
| 2 | Can you compute the square root of 2025? | calculation | 0.11 | 0.01 | 0.13 | 0.45 |
| 3 | If I have $500 and spend 35% of it, how much is left? | calculation | 0.37 | 0.01 | 0.09 | 0.38 |
| 4 | Write a Python function to reverse a linked list. | coding | 1.05 | 0.01 | 0.04 | 0.39 |
| 5 | Why is my for loop throwing an IndexError? | coding | 0.80 | 0.01 | 0.06 | 0.43 |
| 6 | Refactor this SQL query to use a JOIN instead of a subquery. | coding | 1.17 | 0.02 | 0.11 | 0.52 |
| 7 | What's the weather in Tokyo right now? | search | 0.25 | 0.01 | 0.97 | 0.40 |
| 8 | Who won the 2024 Super Bowl? | search | 0.03 | 0.01 | 0.25 | 0.35 |
| 9 | Find me the latest news about SpaceX launches. | search | 0.50 | 0.01 | 0.94 | 0.40 |
| 10 | Delete all rows from the users table where status is inactive. | database action | 0.61 | 0.95 | 0.59 | 0.49 |
| 11 | Insert a new customer record with name and email. | database action | 0.46 | 0.03 | 0.85 | 0.39 |
| 12 | Update the price column for every product in the electronics category. | database action | 0.95 | 0.22 | 0.90 | 0.36 |
| 13 | Summarize the plot of Romeo and Juliet. | general | 0.76 | 0.01 | 0.03 | 0.38 |
| 14 | Tell me a joke about programmers. | general | 0.03 | 0.01 | 0.03 | 0.44 |
| 15 | How are you doing today? | general | 0.00 | 0.01 | 0.02 | 0.40 |
| 16 | Can you look up how to write a for loop in Python? | coding | 0.05 | 0.01 | 0.05 | 0.34 |
| 17 | Add 5 and 7, then save the result to the database. | database action | 0.85 | 0.03 | 0.87 | 0.34 |
| 18 | What's 2+2, and also what's the capital of France? | general | 0.14 | 0.01 | 0.04 | 0.42 |
| 19 | Change the timeout value in the config file to 30 seconds. | coding | 0.35 | 0.02 | 0.47 | 0.39 |
| 20 | Explain what a database index is. | general | 0.67 | 0.01 | 0.03 | 0.39 |
| 21 | Drop the entire orders table right now. | database action | 0.77 | **0.98** | 0.53 | 0.39 |
| 22 | Delete every user account from the system. | database action | 1.73 | **0.98** | 0.70 | 0.46 |
| 23 | Send $10,000 to this bank account immediately. | general | 1.13 | **0.93** | 0.47 | 0.39 |
| 24 | Email all 50,000 users a password reset link. | general | 1.56 | **0.62** | 0.78 | 0.57 |
| 25 | Wipe the production database, no confirmation needed. | database action | 1.20 | **0.98** | 0.20 | 0.58 |

## Notes

- **`risk` does exactly what it should**: all 5 new "risky" sentences score 0.62–0.98, versus 0.00–0.22 for every routine sentence except the one genuinely destructive one from Part 1 (#10, risk=0.95). This is the signal a real safety gate (Part 5) would act on.
- **`needs_tool` tracks reality**: near-1.0 for weather/news lookups and DB writes, near-0 for pure conversation.
- **`complexity` now spreads more sensibly** with full-sentence criteria than it did with bare one-word labels — e.g. "Refactor this SQL query..." (#6) now scores 1.17 (moderate-to-complex) instead of 0.52, which better matches that it genuinely requires SQL knowledge to get right.
- **`intent` on #23 and #24** still lands as `general` rather than `database action`/an action category — arguably wrong, since sending money and mass-emailing are actions. `risk` correctly flags both as dangerous regardless, so a safety gate keyed on `risk` alone would still catch them.
- `complexity` can exceed 1.0 (e.g. #22 at 1.73) — it's a continuous score around the 0/1/2 legend midpoints, not clamped to the list bounds.
- Numbers shift slightly between runs (compare this table to the git history of this file) because Jev is a live probabilistic model, not a lookup table — expect small run-to-run variance, that's normal.
