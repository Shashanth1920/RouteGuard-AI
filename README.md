# routeguard-ai

A router that reads a user's message and decides what to do with it — is it
math, code, a web search, a database change, a real-world action, or just
conversation — using [Jev](https://openrouter.ai/typesafe/jev-1.13), a
decision model from TypeSafe AI (not a text-generating LLM like GPT).

## Architecture

The pipeline has two stages, deliberately kept separate: an AI stage that
only reports facts, and a plain-code stage that makes the actual decision.

```
                      User message
                            │
                            ▼
      ┌───────────────────────────────────────────┐
      │              DECISION ENGINE              │
      │      app/decision/jev_classifier.py       │
      │                                           │
      │ 1 Jev API call, 4 questions asked         │
      │ at once: intent, complexity, risk,        │
      │ needs_tool                                │
      │                                           │
      │ Jev unreachable or errors?                │
      │ -> returns a fail-safe form                │
      │                                           │
      │ (reports facts only - never decides       │
      │  where a request goes)                    │
      └───────────────────────────────────────────┘
                            │  fills out
                            ▼
      ┌───────────────────────────────────────────┐
      │           DECISION  (the form)            │
      │    app/decision/schemas.py - Pydantic     │
      │                                           │
      │ intent            + confidence            │
      │ complexity_score  + complexity_label      │
      │ risk              (0.0 - 1.0)             │
      │ needs_tool        (0.0 - 1.0)             │
      │ is_fallback       (True if Jev failed)    │
      └───────────────────────────────────────────┘
                            │  read by
                            ▼
      ┌───────────────────────────────────────────┐
      │                  ROUTER                   │
      │           app/routing/router.py           │
      │                                           │
      │ 6 plain Python rules, first match         │
      │ wins, checked top to bottom               │
      │                                           │
      │ 0 API calls, 0 AI - pure,                 │
      │ deterministic code                        │
      └───────────────────────────────────────────┘
                            │  produces
                            ▼
      ┌───────────────────────────────────────────┐
      │                ROUTERESULT                │
      │                                           │
      │ route   (1 of the 4 destinations)         │
      │ reason  (e.g. "risk 0.95 >= 0.5")         │
      │ rule    (which of the 6 fired)            │
      └───────────────────────────────────────────┘
                            │  then routes to:
          ▼                     ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   human_review   │  │    strong_llm    │  │      agent       │  │    small_llm     │
│    (a person)    │  │   (smart LLM)    │  │ (tool/DB/search) │  │   (cheap LLM)    │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

**The 6 router rules** — checked in order, first match wins, safety before cost:

```
 Decision
    │
    ▼
 1. is_fallback?                 ──yes──▶ human_review   "Jev failed — can't assess, treat as emergency"
    │ no
    ▼
 2. risk ≥ RISK_CUTOFF (0.5)?    ──yes──▶ human_review   "too risky to hand to any model"
    │ no
    ▼
 3. intent_confidence < 0.7?     ──yes──▶ strong_llm     "Jev itself is unsure — use the smarter model"
    │ no
    ▼
 4. complexity == "complex"?     ──yes──▶ strong_llm     "hard request — needs real reasoning"
    │ no
    ▼
 5. needs_tool ≥ 0.4?            ──yes──▶ agent          "needs a calculator / database / search"
    │ no
    ▼
 6. otherwise                    ────────▶ small_llm     "simple, safe, confident, no tool — cheap is fine"
```

Why this order matters: "delete all users" is *simple* to execute and
would look cheap to a rule that checked complexity first — but it's also
destructive. Risk is checked at rule 2, before anything about cost, so a
dangerous-but-easy request can never slip through to the cheap model
just because it looked simple.

## Folder layout

```
routeguard-ai/
├── app/
│   ├── config.py              API key, model, timeout, router cutoffs — all in one place
│   ├── decision/
│   │   ├── schemas.py         The Decision "form" (Pydantic)
│   │   └── jev_classifier.py  Calls Jev, fills the form, fail-safe on error
│   └── routing/
│       └── router.py          Pure-Python rules: Decision -> RouteResult (no AI, no API calls)
├── tests/
│   ├── test_decisions.py      Fake-Jev tests (no network) + a few real Jev calls
│   └── test_routing.py        Hand-made Decisions, no network at all
├── hello_jev.py                Part 1: first working call to Jev (1 question: intent)
├── decision_engine.py           Part 2 script: 4 questions per message in a single call
├── run_pipeline.py               Runs 25 sentences through classify() + route(), prints the table
├── results/
│   ├── part1.md                 Part 1 input/output + write-up
│   ├── part2.md                 Part 2 input/output + write-up, incl. fix history
│   └── part2_router.md          Router: 25-sentence table, cutoff reasoning, verification
├── experiments/                 Raw JSON responses saved from real runs (proof of work)
├── TASKS.md                     8-part build checklist, checked off as we go
├── .env                         Your OpenRouter API key (not committed — see .gitignore)
└── venv/                        Python virtual environment (not committed)
```

## Setup

```
python -m venv venv
venv\Scripts\activate
pip install requests python-dotenv pydantic pytest
```

Put your key in `.env`:
```
OPENROUTER_API_KEY=your_key_here
```

## Run it

```
venv\Scripts\python.exe hello_jev.py        # Part 1: intent only
venv\Scripts\python.exe decision_engine.py  # Part 2 script: intent + complexity + risk + needs_tool
venv\Scripts\python.exe run_pipeline.py     # engine + router together, on all 25 sentences
venv\Scripts\python.exe -m pytest tests/ -v # 23 tests (fake ones need no API key)
```

## What's been done — in plain terms

Think of the end goal as a **receptionist for an AI system**: someone sends
a message, and before anything expensive happens, the receptionist reads it
and decides who should actually handle it — a calculator, a coder, a search
tool, a database, or just a chat reply. That receptionist is Jev.

**Part 1** proved the basic wiring works: send Jev a sentence, ask it one
question ("what's the intent — math, code, search, database, or general
chat?"), and get back an answer with a confidence score. Tested on 20
sentences, including some deliberately confusing ones. 18 of 20 landed
correctly, and the model appropriately said it was less confident on the
confusing ones — a good sign it's not just guessing randomly.
→ Details: [results/part1.md](results/part1.md)

**Part 2** made the receptionist ask 4 questions about each message
instead of 1, in a single request (so it's not 4x slower):
- **intent** — what kind of request is this (now 6 options, after adding
  "action" for things like sending money or mass emails)
- **complexity** — how hard is this to actually do
- **risk** — could this cause real damage if done wrong (deleting data,
  sending money, emailing everyone)
- **needs_tool** — does this need a calculator/database/search, or can it
  just be answered in words

Tested on the original 20 sentences plus 5 deliberately dangerous ones
("drop the orders table", "send $10,000", "wipe the database"). The `risk`
question worked very well — it correctly flagged all 5 dangerous sentences
as high risk (0.93–0.99) while routine ones stayed low. That's the exact
signal a future "safety gate" (Part 5) needs to stop something destructive
before it happens.

Two rough edges got caught during review and partly fixed:
- Jev is bad at math itself, so `needs_tool` needed to more strongly flag
  arithmetic as needing a calculator. Fixed the wording — it helped, but
  not completely (still an open item).
- Two sentences about moving money and mass-emailing were wrongly
  classified as harmless "general chat." Added a 6th intent option,
  "action," which fixed both.

→ Full before/after numbers and an explanation of how to independently
verify these results are real (not made up): [results/part2.md](results/part2.md)

This got promoted into a real module (`app/decision/`) with a proper
`Decision` form: a `Pydantic` model that rejects bad data (an unrecognized
intent, a risk value outside 0–1) instead of silently passing it through,
plus an `is_fallback` flag so a Jev failure is never confused with a
genuinely high-risk request in the logs later — a "receptionist was
absent, treated as an emergency" note, not just "emergency."

**The Router** is the hospital rulebook: given a filled-out `Decision`, 6
plain Python `if` statements — no AI, no API calls — decide where the
request goes: `human_review`, `strong_llm`, `agent`, or `small_llm`.
Safety checks run first, so something simple-but-dangerous (like "delete
all users") can't slip past the risk check just because it looked cheap
to answer. Every decision comes with a written reason
("risk 0.95 ≥ 0.5") so it can be logged and explained later, not just
acted on silently. All 3 cutoffs that tune this (how much risk is too
much, how unsure is "unsure," etc.) live in `app/config.py`, chosen from
real numbers on the 25 test sentences — not guessed.
→ Full 25-sentence table, cutoff reasoning, and verification:
[results/part2_router.md](results/part2_router.md)

## Progress

See [TASKS.md](TASKS.md) for the full 8-part plan. Parts 1–2 are done —
the Decision Engine reports facts, the Router decides where a request
goes, and 23 tests cover both without needing an API key for most of
them. Part 3 (FastAPI + LLMs — actually wiring the 4 destinations up to
real models) is next.
