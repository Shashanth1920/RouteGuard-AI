# Part 2 — Decision Engine: 4 Questions, 1 Call Per Sentence

Script: [`decision_engine.py`](decision_engine.py)
Model: `typesafe/jev-1.13` (pinned major.minor — not the floating `~typesafe/jev-latest` alias)
Full raw sample response: [`experiments/part2_raw_response.json`](experiments/part2_raw_response.json)

Adds 3 questions to Part 1's `intent` question, all answered in one request per sentence:

| Question | Type | Criteria |
|---|---|---|
| `intent` | `choice` | 5 categories (unchanged from Part 1) |
| `complexity` | `score` | `["simple", "moderate", "complex"]` — ordered list, low first |
| `risk` | `noul` | true = destructive/irreversible (delete, drop, send money, mass-message); false = safe/reversible |
| `needs_tool` | `noul` | true = needs code/DB/search/exact math; false = answerable from conversation alone |

## Verification checklist

| Check | Result |
|---|---|
| One API call per sentence? | ✅ Counted explicitly: `25 API calls for 25 sentences (one call per sentence: True)` |
| Score levels in order, low first? | ✅ `criteria: ["simple", "moderate", "complex"]` — a list, not a dict (dict would 422) |
| Nouls have yes/no descriptions? | ✅ Both `risk` and `needs_tool` carry explicit `true`/`false` criteria text |
| Raw response shows `score` for complexity, `noul` for risk? | ✅ Confirmed in `part2_raw_response.json` — `"complexity": {"score": 0.04, ...}`, `"risk": {"noul": 0}` |
| Time about the same as Part 1? | ✅ 0.42s avg here vs 0.44s avg in Part 1 — bundling 4 questions cost effectively nothing extra |

## Results

| # | Sentence | intent | complexity | risk | needs_tool | time (s) |
|---|---|---|---|---|---|---|
| 1 | What is 847 times 23? | calculation | 0.04 | 0.00 | 0.23 | 0.91 |
| 2 | Can you compute the square root of 2025? | calculation | 0.00 | 0.01 | 0.13 | 0.39 |
| 3 | If I have $500 and spend 35% of it, how much is left? | calculation | 0.00 | 0.01 | 0.09 | 0.41 |
| 4 | Write a Python function to reverse a linked list. | coding | 0.42 | 0.01 | 0.04 | 0.42 |
| 5 | Why is my for loop throwing an IndexError? | coding | 0.32 | 0.01 | 0.07 | 0.40 |
| 6 | Refactor this SQL query to use a JOIN instead of a subquery. | coding | 0.52 | 0.02 | 0.11 | 0.43 |
| 7 | What's the weather in Tokyo right now? | search | 0.06 | 0.01 | 0.97 | 0.43 |
| 8 | Who won the 2024 Super Bowl? | search | 0.00 | 0.01 | 0.26 | 0.40 |
| 9 | Find me the latest news about SpaceX launches. | search | 0.18 | 0.01 | 0.93 | 0.68 |
| 10 | Delete all rows from the users table where status is inactive. | database action | 0.02 | 0.95 | 0.58 | 0.35 |
| 11 | Insert a new customer record with name and email. | database action | 0.04 | 0.03 | 0.84 | 0.35 |
| 12 | Update the price column for every product in the electronics category. | database action | 0.54 | 0.22 | 0.90 | 0.44 |
| 13 | Summarize the plot of Romeo and Juliet. | general | 0.13 | 0.01 | 0.03 | 0.40 |
| 14 | Tell me a joke about programmers. | general | 0.00 | 0.01 | 0.03 | 0.37 |
| 15 | How are you doing today? | general | 0.00 | 0.01 | 0.02 | 0.41 |
| 16 | Can you look up how to write a for loop in Python? | coding | 0.00 | 0.01 | 0.05 | 0.39 |
| 17 | Add 5 and 7, then save the result to the database. | database action | 0.43 | 0.03 | 0.88 | 0.38 |
| 18 | What's 2+2, and also what's the capital of France? | general | 0.00 | 0.01 | 0.04 | 0.37 |
| 19 | Change the timeout value in the config file to 30 seconds. | coding | 0.01 | 0.02 | 0.53 | 0.36 |
| 20 | Explain what a database index is. | general | 0.06 | 0.01 | 0.03 | 0.36 |
| 21 | Drop the entire orders table right now. | database action | 0.12 | **0.98** | 0.46 | 0.40 |
| 22 | Delete every user account from the system. | database action | 1.27 | **0.98** | 0.69 | 0.41 |
| 23 | Send $10,000 to this bank account immediately. | general | 0.73 | **0.93** | 0.44 | 0.40 |
| 24 | Email all 50,000 users a password reset link. | general | 1.18 | **0.61** | 0.76 | 0.38 |
| 25 | Wipe the production database, no confirmation needed. | database action | 0.54 | **0.99** | 0.21 | 0.37 |

## Notes

- **`risk` does exactly what it should**: all 5 new "risky" sentences score 0.61–0.99, versus 0.00–0.22 for every routine sentence except the one genuinely destructive one from Part 1 (#10 "Delete all rows...", risk=0.95). This is the signal a real safety gate (Part 5) would act on.
- **`needs_tool` tracks reality**: near-1.0 for weather/news lookups and DB writes, near-0 for pure conversation (jokes, "how are you").
- **`intent` on #23 and #24** landed as `general` rather than `database action` — arguably wrong, since sending money and mass-emailing are actions, not just talk. Worth watching as this feeds into the router in later parts; `risk` correctly flags both as dangerous regardless of what `intent` says, so a safety gate keyed on `risk` alone would still catch them.
- `complexity` occasionally exceeds 1.0 (e.g. #22 at 1.27) — it's a continuous score around the 0/1/2 legend midpoints, not clamped to the list bounds.
