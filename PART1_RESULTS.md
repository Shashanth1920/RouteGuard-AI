# Part 1 — Jev Hello-World: Input & Output

Script: [`hello_jev.py`](hello_jev.py)
Model: `typesafe/jev-1.13` — **the real Jev decision model** (TypeSafe AI, released Sept 15 2026), called via OpenRouter's `/api/alpha/decisions` endpoint.
Full raw sample response: [`experiments/sample_raw_response.json`](experiments/sample_raw_response.json)

Earlier versions of this script mistakenly called the generic OpenAI chat completions endpoint. Jev is a different kind of model — a "System One" decision model. It doesn't generate text; you send it a `state` (the message) plus typed `questions` with `criteria` describing each possible answer, and it returns a typed choice with a native confidence score and per-option probabilities — no prompt engineering or JSON parsing needed.

## Results

| # | Input sentence | Category (intended) | Intent (returned) | Confidence | Time (s) |
|---|---|---|---|---|---|
| 1 | What is 847 times 23? | calculation | calculation | 1.00 | 1.12 |
| 2 | Can you compute the square root of 2025? | calculation | calculation | 1.00 | 0.33 |
| 3 | If I have $500 and spend 35% of it, how much is left? | calculation | calculation | 1.00 | 0.39 |
| 4 | Write a Python function to reverse a linked list. | coding | coding | 1.00 | 0.38 |
| 5 | Why is my for loop throwing an IndexError? | coding | coding | 1.00 | 0.34 |
| 6 | Refactor this SQL query to use a JOIN instead of a subquery. | coding | coding | 1.00 | 0.48 |
| 7 | What's the weather in Tokyo right now? | search | search | 1.00 | 0.44 |
| 8 | Who won the 2024 Super Bowl? | search | search | 1.00 | 0.37 |
| 9 | Find me the latest news about SpaceX launches. | search | search | 1.00 | 0.40 |
| 10 | Delete all rows from the users table where status is inactive. | database action | database action | 1.00 | 0.37 |
| 11 | Insert a new customer record with name and email. | database action | database action | 1.00 | 0.42 |
| 12 | Update the price column for every product in the electronics category. | database action | database action | 1.00 | 0.40 |
| 13 | Summarize the plot of Romeo and Juliet. | general | general | 1.00 | 0.37 |
| 14 | Tell me a joke about programmers. | general | general | 1.00 | 0.41 |
| 15 | How are you doing today? | general | general | 1.00 | 0.34 |
| 16 | Can you look up how to write a for loop in Python? | *ambiguous* (search vs. coding) | coding | 0.97 | 0.46 |
| 17 | Add 5 and 7, then save the result to the database. | *ambiguous* (calculation vs. database action) | database action | 0.81 | 0.40 |
| 18 | What's 2+2, and also what's the capital of France? | *ambiguous* (calculation vs. search) | general | 0.43 | 0.37 |
| 19 | Change the timeout value in the config file to 30 seconds. | *ambiguous* (database action vs. coding) | coding | 0.81 | 0.41 |
| 20 | Explain what a database index is. | *ambiguous* (general vs. database action) | general | 0.91 | 0.38 |

## Summary

- 20/20 sentences returned a valid intent — no parse errors, because the API returns a structured typed answer directly (no free-text to parse).
- 15/15 unambiguous sentences: **perfect confidence (1.00)** on every one.
- 5/5 ambiguous sentences got a defensible answer, and confidence correctly tracked difficulty — dropping to 0.43 on the genuinely two-intents-in-one sentence (#18: "What's 2+2, and also what's the capital of France?").
- Response time: 0.33s–1.12s, average ~0.44s — roughly **3x faster** than the earlier GPT-4o-mini version (~1.3s avg), consistent with Jev's advertised 70–500ms latency.
