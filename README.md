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
│   ├── main.py                 Creates the FastAPI app
│   ├── config.py              API key, model, timeout, router cutoffs — all in one place
│   ├── api/
│   │   └── routes.py           POST /v1/route, GET /health — thin, no routing/LLM logic of its own
│   ├── decision/
│   │   ├── schemas.py         The Decision "form" (Pydantic)
│   │   └── jev_classifier.py  Calls Jev, fills the form, fail-safe on error
│   ├── routing/
│   │   └── router.py          Pure-Python rules: Decision -> RouteResult (no AI, no API calls)
│   ├── llm/
│   │   └── client.py           call_llm() + get_answer(): route -> model, backup on failure
│   ├── tools/
│   │   ├── calculator.py       Safe AST-based math evaluator — no eval()
│   │   ├── search.py           Tavily web search — top 3 results, treated as untrusted data
│   │   ├── database.py         Fake in-memory 10-user list — list/read/delete + reset()
│   │   └── registry.py         Every tool + its name/description/risk/destructive label + param schema
│   ├── agents/
│   │   └── agent.py            Hand-built LangGraph agent: think -> propose_tool -> execute_tool loop
│   ├── safety/
│   │   └── gate.py             The pharmacist: 2 Jev questions per proposed tool call, before it runs
│   └── db/
│       └── logging.py          The record book: save_request(), get_request(), get_stats() - fail-open
├── tests/
│   ├── test_decisions.py      Fake-Jev tests (no network) + a few real Jev calls
│   ├── test_routing.py        Hand-made Decisions, no network at all
│   ├── test_api.py             FastAPI TestClient + fake classify() — no network
│   ├── test_llm.py             Fake call_llm() — no network, proves human_review = 0 LLM calls
│   ├── test_tools.py           Calculator/search/database/registry — no real API calls
│   ├── test_agent.py           Scripted fake LLM + fake gate — no network, proves loop/stop/block behavior
│   ├── test_gate.py            Fake Jev — no network, proves ALLOW/NEEDS_APPROVAL/BLOCK rules
│   └── test_db.py              Real Postgres, dedicated routeguard_test DB — skips if unreachable
├── hello_jev.py                Part 1: first working call to Jev (1 question: intent)
├── decision_engine.py           Part 2 script: 4 questions per message in a single call
├── run_pipeline.py               Runs 25 sentences through classify() + route(), prints the table
├── results/
│   ├── part1.md                 Part 1 input/output + write-up
│   ├── part2.md                 Part 2 input/output + write-up, incl. fix history
│   ├── part2_router.md          Router: 25-sentence table, cutoff reasoning, verification
│   ├── part4_agent.md           Agent: live tool-use examples, tests
│   ├── part5_gate.md            Safety Gate: live examples, injection demo, tests
│   └── part6_logging.md         Logging: fail-open proof, 10-request verification, a real bug caught
├── evaluation/
│   ├── label_guide.md            Definitions for every label + why (dev/test split, tricky cases)
│   ├── build_dataset.py           Generates dev.json + test.json (250 hand-labeled rows) - reviewable, rerunnable
│   ├── build_gate_cases.py        Generates gate_cases.json (30 hand-labeled proposed tool calls)
│   ├── dev.json                   100 rows — for tuning, not final scoring
│   ├── test.json                  150 rows — untouched until the final Part 7 run
│   └── gate_cases.json            30 rows — expected ALLOW/NEEDS_APPROVAL/BLOCK per case
├── experiments/                 Raw JSON responses saved from real runs (proof of work)
├── TASKS.md                     8-part build checklist, checked off as we go
├── .env                         API keys + DB credentials (not committed — see .gitignore)
└── venv/                        Python virtual environment (not committed)
```

## Setup

```
python -m venv venv
venv\Scripts\activate
pip install requests python-dotenv pydantic pytest fastapi uvicorn httpx langgraph psycopg2-binary
```

Part 6 needs a running PostgreSQL (this project uses a native local
install; Docker works the same way). Create a dedicated role + 2
databases (main + test), then put its credentials in `.env` as
`DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_TEST_NAME`/`DB_USER`/`DB_PASSWORD`.

Put your key in `.env`:
```
OPENROUTER_API_KEY=your_key_here
```

## Run it

```
venv\Scripts\python.exe hello_jev.py        # Part 1: intent only
venv\Scripts\python.exe decision_engine.py  # Part 2 script: intent + complexity + risk + needs_tool
venv\Scripts\python.exe run_pipeline.py     # engine + router together, on all 25 sentences
venv\Scripts\python.exe -m pytest tests/ -v # 73 tests (fake ones need no API key or database)
venv\Scripts\python.exe -m uvicorn app.main:app --port 8000  # web service; open http://localhost:8000/docs
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

**Part 3, Step 1** puts the whole thing behind a web front door with
[FastAPI](https://fastapi.tiangolo.com/): `POST /v1/route` takes a
message and returns the decision, the route, and why — over HTTP, so
any app can use it, not just Python scripts run by hand. `GET /health`
is a heartbeat check for later (Docker will poll it in Part 8). The
endpoint is deliberately "thin" — `app/api/routes.py` only calls
`classify()` then `route()`, no logic of its own; if a rule needs to
change, it changes in `router.py`, never here. The endpoint function is
a plain `def`, not `async def` — `classify()` uses `requests`, which
blocks the current thread while waiting on Jev, and FastAPI runs plain
`def` endpoints in a worker thread pool so one slow Jev call doesn't
freeze every other user's request. `async def` would have looked fine
locally with one user and then serialized every request in production.
Verified live: `Delete all users` → real Jev call → `human_review`
(risk 0.97), an empty message → `422` rejected automatically before it
ever reaches Jev, both through the actual running server, not just tests.
→ [app/main.py](app/main.py), [app/api/routes.py](app/api/routes.py)

**Part 3, Step 2** hires the 2 doctors: `small_llm` now calls
`openai/gpt-5.6-luna` (cheap, fast), `strong_llm` calls
`openai/gpt-5.6-terra` (~10x the price, smarter). `agent` and
`human_review` never touch an LLM at all — `human_review` in particular
is a hard safety requirement (a risky request must never get quietly
answered anyway), proven by a dedicated test that asserts zero calls
happen. If the cheap model fails, it's retried once on the strong model;
if the strong model fails, you get a clean `error` field, never a crash.
Same-question cost comparison, run for real: terra cost **~14x more**
than luna and took 1.6x longer for a question neither model needed deep
reasoning for — the exact case for routing most traffic to the cheap
model. Full numbers, live 3-scenario check, and an honestly-reported
miss (the "explain the financial report risks" example routed to
`small_llm`, not `strong_llm`, because Jev scored it "moderate" not
"complex"): [results/part3_llm.md](results/part3_llm.md)

**Part 4, Step 1** builds the `agent` route's equipment, before the agent
itself exists: `calculator` (low risk, safe AST parser — no `eval()`,
confirmed by grep and by trying to break it: `__import__('os')`,
`os.system(1)`, `1==1` all rejected; division by zero is a clean error,
not a crash), `search` (medium risk, real [Tavily](https://tavily.com/)
calls, results treated as plain untrusted data, never as instructions —
that's what stops prompt injection hidden in a webpage from doing
anything), and `database` (high risk, a fake in-memory list of 10 users
so `delete_user` can be tested for real without ever touching real
data). Every tool is registered in `app/tools/registry.py` with a name,
description, and risk label (`delete_user` marked `destructive`) —
labels Part 5's Safety Gate will read the same way a hospital locks
drawers based on what's inside them, without needing to know how the
drawer works.

Stress-testing the calculator by hand caught something the "reject
`eval()`" tests didn't: `2 ** 999999999999` is *valid* arithmetic, not
a code-injection attempt, but Python's bigint `pow()` spent unbounded
memory computing it — it grew a process to several GB before being
killed. Fixed by capping the exponent; now it's rejected instantly, with
a regression test.
→ [app/tools/](app/tools/), [tests/test_tools.py](tests/test_tools.py)

**Part 4, Step 2** hires the doctor to use that equipment: a
[LangGraph](https://langchain-ai.github.io/langgraph/) agent, hand-built
with `StateGraph` (not the prebuilt `create_react_agent`), because
"propose a tool" and "execute a tool" have to be 2 separate steps —
Part 5's Safety Gate goes right between them later, like a nurse
checking a prescription before the medicine is given. The graph loops
`think → propose_tool → execute_tool → think` until the model is ready
to `answer`, capped at 5 steps so a confused agent can't call tools (and
spend real money) forever. `delete_user` is temporarily hardcoded-blocked
in `execute_tool` — Part 5 replaces that lock with real Jev-based
judgment, not the graph shape.

Verified live, real models, real tools: "847 times 23" → calculator →
19,481; "weather in Tokyo" → real Tavily search → correct answer (one
result's content looked like unrelated odds-market text — ignored, not
followed, exactly the prompt-injection defense point); calling the
agent directly with "delete user 3" → blocked, the fake user is still
there afterward. One honestly-reported miss: "List all users" landed on
`strong_llm` instead of `agent` because Jev's intent confidence (0.68)
fell just under the router's cutoff — rephrasing to name the tool
explicitly fixed it. Through the full API, "Delete user 3" never even
reaches the agent — the router's own risk check (Part 2) catches it
first, `human_review`, zero calls — the destructive-tool lock in the
agent is a second layer, not the only one.
→ [results/part4_agent.md](results/part4_agent.md)

**Part 5** replaces the agent's temporary "block every destructive tool"
lock with the real thing: a Safety Gate (`app/safety/gate.py`) that runs
inside `execute_tool` - the only place any tool's function is ever
called - and asks Jev 2 questions about *this specific proposed call*:
is it destructive, and does it actually match what the user asked for.
First match wins: Jev failure → `NEEDS_APPROVAL`, mismatch → `BLOCK`,
tool marked destructive → `NEEDS_APPROVAL` (never automatic), Jev flags
this call as risky → `NEEDS_APPROVAL`, else → `ALLOW`.

Why the router (Part 2) alone isn't enough: it only ever sees the user's
original message, decided once, up front. The agent can decide things on
its own afterward - including after reading a tool result - so only a
check running right before each tool executes can catch something the
agent talks itself into. Confirmed live with the exact "same tool,
different scope" case the spec calls out: updating 1 product's price
scored destructive 0.08, updating every product in a category scored
0.93 - same registry label, very different real risk.

The injection demo: fed the agent a fake, poisoned search result
instructing it to delete a user, for real, 3 times with increasingly
aggressive wording. All 3 times `openai/gpt-5.6-luna` recognized it as
untrusted tool content and refused - a real result, not staged. Since
the model defended itself, the gate never got a live end-to-end block to
show off, so its own defense was verified independently: `check_gate()`
called directly with the exact mismatch shape a successful injection
would produce returned `BLOCK` with a real Jev call (match score 0.01).
Both layers verified, not just the one that held.
→ [results/part5_gate.md](results/part5_gate.md)

**Part 6** is the hospital's record book: every API request gets saved to
PostgreSQL after its answer is ready - `requests` (Jev's 4 answers, the
route/rule/reason, model/tokens/cost, and Jev time/LLM time/total time,
kept separate) and `tool_calls` (one row per tool call, linked by
`request_id`, with the gate's result/reason/scores/time and whether it
actually ran). Docker wasn't installed on this machine, so this runs
against a native local PostgreSQL 18 install instead - same role a
`postgres` container would play here.

**Key design point: logging fails open, safety fails closed.** When
`save_request()` can't reach the database, it prints a warning and moves
on - it never raises, because a missing log row is a much smaller problem
than refusing to answer the user over an observability hiccup. Verified
live by pointing the running app at an unreachable database (the same
real failure a stopped database produces): `POST /v1/route` still
returned `200 OK` with a real answer, alongside 2 clear warnings in the
server log.

Building this caught a real, unstaged bug: one logged record showed a
**negative** `llm_time` and a `total_time` smaller than `jev_time` alone -
impossible, since total time wraps the whole request. Every duration in
this codebase was measured with `time.time()` (wall-clock, which can jump
backward on an NTP sync) instead of `time.monotonic()` (guaranteed
monotonic). Fixed everywhere; re-verified with a clean 10-request batch -
every timing came back positive and consistent.

Sent 10 real mixed requests and answered the 4 required questions from
real logged data (route counts, total cost, avg Jev vs. LLM time, tool
calls blocked) - cross-checked against the new `GET /v1/stats` endpoint,
which matched exactly. `GET /v1/requests/{id}` (also a "nice extra")
returns one full record, request + its tool calls, step-ordered.
→ [results/part6_logging.md](results/part6_logging.md)

**Part 7, Step 1** builds the test dataset - this is a hospital inspection
bringing 200+ fake patients with known correct answers, to check whether
the real thing routes them correctly. 250 messages across 8 categories
(calculation, search, database read/write, risky/destructive, general
chat, coding, and 45 deliberately **tricky** cases: scary-sounding but
safe, polite-but-dangerous, hidden danger, mixed requests, typos,
Hinglish/Tanglish code-mixing, and very long/short messages), plus 30
separate proposed-tool-call cases with expected Safety Gate verdicts.

Every label was written from `evaluation/label_guide.md`'s own
definitions - never by running Jev and copying its answers, since that
would just be grading Jev against itself. Split 100 dev (for tuning) /
150 test (untouched until the final run), stratified per category, with
zero duplicates and zero overlap with the original 25 sentences from
Part 2 (checked programmatically, not just by eye).

**This is a draft, not yet finished per the spec's own instruction**:
Claude drafted every label; a human still needs to personally skim all
250+30 rows and check at least 50 carefully before this is real ground
truth. One row (`tric-044`, the bare word "delete") is flagged in its own
notes as a genuine judgment call worth a second look.
→ [evaluation/label_guide.md](evaluation/label_guide.md)

## Progress

See [TASKS.md](TASKS.md) for the full 8-part plan. Parts 1–6 are done —
Jev decides, the router picks a destination, 2 LLMs answer directly, a
LangGraph agent uses real tools behind a real Jev-backed Safety Gate, and
every request and tool call is now logged to PostgreSQL (fail-open, no
secrets, truncated outputs). 73 tests total, no API key needed for most
of them. Part 7 Step 1 (the labeled evaluation dataset) is drafted and
needs your review before Step 2 (running the real evaluation) can start.
