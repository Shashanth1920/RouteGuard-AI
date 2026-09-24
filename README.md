# routeguard-ai

A router that reads a user's message and decides what to do with it — is it
math, code, a web search, a database change, a real-world action, or just
conversation — using [Jev](https://openrouter.ai/typesafe/jev-1.13), a
decision model from TypeSafe AI (not a text-generating LLM like GPT).

## Folder layout

```
routeguard-ai/
├── hello_jev.py          Part 1: first working call to Jev (1 question: intent)
├── decision_engine.py    Part 2: 4 questions per message in a single call
├── results/
│   ├── part1.md          Part 1 input/output + write-up
│   └── part2.md          Part 2 input/output + write-up, incl. fix history
├── experiments/          Raw JSON responses saved from real runs (proof of work)
├── TASKS.md              8-part build checklist, checked off as we go
├── .env                  Your OpenRouter API key (not committed — see .gitignore)
└── venv/                 Python virtual environment (not committed)
```

## Setup

```
python -m venv venv
venv\Scripts\activate
pip install requests python-dotenv
```

Put your key in `.env`:
```
OPENROUTER_API_KEY=your_key_here
```

## Run it

```
venv\Scripts\python.exe hello_jev.py        # Part 1: intent only
venv\Scripts\python.exe decision_engine.py  # Part 2: intent + complexity + risk + needs_tool
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

## Progress

See [TASKS.md](TASKS.md) for the full 8-part plan. Parts 1–2 (decision
engine half) are done; the "+ Router" half of Part 2 — actually sending
each message to the right handler based on Jev's answer — is next.
