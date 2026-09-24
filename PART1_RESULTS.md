# Part 1 — Jev Hello-World: Input & Output

Script: [`hello_jev.py`](hello_jev.py)
Model: `openai/gpt-4o-mini` (via OpenRouter chat completions)
Full raw sample response: [`experiments/sample_raw_response.json`](experiments/sample_raw_response.json)

Uses a `requests.Session()` so all 20 calls reuse one TCP/TLS connection instead of opening a new one per request — cut average latency from ~2.3s to ~1.3s.

## Results

| # | Input sentence | Category (intended) | Intent (returned) | Confidence | Time (s) |
|---|---|---|---|---|---|
| 1 | What is 847 times 23? | calculation | calculation | 0.95 | 2.51 |
| 2 | Can you compute the square root of 2025? | calculation | calculation | 0.95 | 1.68 |
| 3 | If I have $500 and spend 35% of it, how much is left? | calculation | calculation | 0.95 | 1.92 |
| 4 | Write a Python function to reverse a linked list. | coding | coding | 0.95 | 1.39 |
| 5 | Why is my for loop throwing an IndexError? | coding | coding | 0.90 | 1.68 |
| 6 | Refactor this SQL query to use a JOIN instead of a subquery. | coding | coding | 0.90 | 0.97 |
| 7 | What's the weather in Tokyo right now? | search | search | 0.90 | 1.18 |
| 8 | Who won the 2024 Super Bowl? | search | search | 0.90 | 1.92 |
| 9 | Find me the latest news about SpaceX launches. | search | search | 0.90 | 1.00 |
| 10 | Delete all rows from the users table where status is inactive. | database action | database action | 0.95 | 1.48 |
| 11 | Insert a new customer record with name and email. | database action | database action | 0.90 | 1.80 |
| 12 | Update the price column for every product in the electronics category. | database action | database action | 0.90 | 0.93 |
| 13 | Summarize the plot of Romeo and Juliet. | general | general | 0.90 | 1.05 |
| 14 | Tell me a joke about programmers. | general | general | 0.90 | 0.79 |
| 15 | How are you doing today? | general | general | 0.90 | 1.17 |
| 16 | Can you look up how to write a for loop in Python? | *ambiguous* (search vs. coding) | search | 0.90 | 0.88 |
| 17 | Add 5 and 7, then save the result to the database. | *ambiguous* (calculation vs. database action) | database action | 0.80 | 1.62 |
| 18 | What's 2+2, and also what's the capital of France? | *ambiguous* (calculation vs. search) | calculation | 0.90 | 0.94 |
| 19 | Change the timeout value in the config file to 30 seconds. | *ambiguous* (database action vs. coding) | database action | 0.80 | 1.55 |
| 20 | Explain what a database index is. | *ambiguous* (general vs. database action) | general | 0.90 | 1.30 |

## Summary

- 20/20 sentences returned a valid, parseable intent — no `PARSE_ERROR`s.
- 15/15 unambiguous sentences landed in their intended category.
- All 5 ambiguous sentences got a defensible answer; confidence dropped noticeably on the two hardest cases (#17, #19 → 0.80 vs. the usual 0.90–0.95), which tracks with them actually being harder to call.
- Response time ranged 0.79s–2.51s per call, average ~1.3s (down from ~2.3s before reusing the HTTP connection across calls).
