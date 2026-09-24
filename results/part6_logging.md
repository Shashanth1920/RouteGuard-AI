# Part 6 — PostgreSQL Logging

The record book. [`app/db/logging.py`](../app/db/logging.py): 2 tables,
one `save_request()` function called once per API request after the answer
is ready, plus 2 read functions backing the "nice extra" endpoints.

## A real deviation from the spec, and why it's fine

Docker isn't installed on this machine. Rather than blocking on installing
it, this uses a **native local PostgreSQL 18** install that was already
present and running as a Windows service on port 5432 - functionally the
same role a `postgres` Docker container would play for this part (Part 8
is where Docker itself becomes the actual subject). A dedicated `routeguard`
role and two databases (`routeguard`, `routeguard_test`) were created for
this project rather than using the machine's `postgres` superuser -
credentials live in `.env` / `app/config.py`, same as every other secret
in this project.

## Why 2 tables instead of 1

One request can have many tool calls - a database is normalized to reflect
that, the same way one patient's chart has many prescriptions, not a chart
that's duplicated once per prescription. Cramming tool calls into the
`requests` row (as repeated columns, or a single JSON blob) would mean an
unbounded, awkward-to-query shape for something that's naturally a
one-to-many relationship. `tool_calls.request_id` is a foreign key back to
`requests.id`, so a request's full story is 2 simple queries (or 1 join)
away.

## Why logging fails open but safety fails closed

They're solving different problems. Safety is about *preventing harm* -
when unsure, the safest default is to stop and ask a human, because acting
on a bad guess could be irreversible. Logging is about *keeping a record*
- when the record book itself is unavailable, the cost of not writing a
row is small and recoverable (you just don't have that entry later), while
refusing to answer the user because the database happened to be down would
turn an observability problem into a real outage for no good reason. Same
principle, opposite defaults, because the two failure modes have very
different costs.

## Why not log everything, including API keys

Two different concerns. First, secrets: `OPENROUTER_API_KEY` and
`TAVILY_API_KEY` are only ever used in `Authorization` headers - they never
appear in any value passed to `save_request()`, and
`test_no_api_key_appears_anywhere_in_saved_data` checks that directly. A
logged key would turn a database backup or a stray query result into a
credential leak. Second, size and privacy: tool outputs are truncated to
`LOG_OUTPUT_MAX_CHARS` (1000) so one large search result or product list
can't bloat every row, and user messages are logged in full - which means
they may contain whatever personal information a user chooses to type.
**This is worth calling out explicitly: `requests.message` is not
scrubbed or anonymized in this implementation.** Anyone with database
access can read every message ever sent. That's an acceptable tradeoff for
a local learning project, not for anything handling real user data without
a retention policy and access controls to go with it.

## Live verification

Sent 10 real mixed requests through the actual running API (joke, math,
a financial-report question, weather, 2 destructive attempts, small talk,
a percentage, and a product listing), then answered the 4 required
questions from the real logged data - not by eyeballing the responses,
by querying the database directly and cross-checking against `GET
/v1/stats`:

```sql
SELECT route, count(*) FROM requests GROUP BY route;
--  agent | human_review | small_llm | strong_llm
--    4   |      2       |     2     |     2

SELECT sum(cost) FROM requests;                          -- 0.0070678
SELECT avg(jev_time), avg(llm_time) FROM requests;        -- 0.619s / 4.232s
SELECT gate_result, count(*) FROM tool_calls GROUP BY gate_result;  -- ALLOW: 5
```

`GET /v1/stats` returned the identical numbers from the running API,
confirming the endpoint and the raw queries agree.

**Tool calls blocked: 0** in this batch - both destructive attempts
("Delete user 3", "Drop the entire orders table right now") were caught by
the *router* (Part 2's risk check) before they ever reached the agent or
the gate, exactly the "router catches it first" story from Parts 4 and 5.
A third attempt, phrased to look conditional/exploratory ("look up user 3
... remove them if their account looks inactive"), was still caught by the
router (risk 0.84). This is an honest result, not a gap: the gate's own
BLOCK/NEEDS_APPROVAL behavior is separately verified, live, in
[results/part5_gate.md](part5_gate.md) (a direct `check_gate()` call) and
in `tests/test_db.py::test_blocked_tool_is_logged_with_executed_false`
(a synthetic case proving it's logged correctly with `executed = false`
when it does happen).

**"DB down → still works":** couldn't stop the Windows Postgres service
directly (no admin rights in this session), so pointed the running app at
an unreachable port instead - the same real failure mode (connection
refused) a stopped database produces. Sent a request with the database
completely unreachable:

```
[routeguard] WARNING: could not initialize the database at startup: connection to server ... Connection refused
[routeguard] WARNING: failed to log request <id> to the database: connection to server ... Connection refused
INFO: 127.0.0.1 - "POST /v1/route HTTP/1.1" 200 OK
```

**200 OK, a real joke answered, two clear warnings, zero crash.**
Restored the real connection afterward and confirmed logging resumed
normally.

## A real bug this caught: `time.time()` vs `time.monotonic()`

Building this surfaced a genuine bug, not something staged: one logged
record showed `llm_time: -0.63` (negative) and `total_time` smaller than
`jev_time` alone - a logical impossibility, since `total_time` wraps the
entire request including the Jev call. `time.time()` returns wall-clock
time, which can jump backward (NTP sync, system clock adjustments) mid-
measurement; every duration in this codebase (`jev_classifier.py`,
`gate.py`, `agent.py`, `llm/client.py`, `routes.py`) was using it to
measure elapsed time. Fixed by switching every `start = time.time()` /
`elapsed = time.time() - start` pair to `time.monotonic()`, which the OS
guarantees never goes backward - the correct tool for measuring durations,
with `time.time()` reserved for actual timestamps (which this project
doesn't generate itself; `created_at` uses Postgres's own `now()`). Re-ran
the same 10-request batch afterward - every timing value came back
positive and consistent (`total_time >= jev_time`, `llm_time > 0`) as it
always should have.

## Tests (`tests/test_db.py`, real Postgres, dedicated `routeguard_test` database)

| Test | Proves |
|---|---|
| `test_normal_request_creates_one_row` | 1 `requests` row, right fields |
| `test_agent_request_with_2_tools_creates_1_request_row_and_2_tool_call_rows` | 1 + 2, correctly linked and step-ordered |
| `test_blocked_tool_is_logged_with_executed_false` | a `NEEDS_APPROVAL` gate result logs `executed = false` |
| `test_database_down_does_not_raise_and_app_still_gets_an_answer` | `save_request()` swallows a simulated connection failure, never raises |
| `test_no_api_key_appears_anywhere_in_saved_data` | neither API key string appears in any saved row |

All 5 skip automatically (rather than failing the suite) if the test
database isn't reachable. 73/73 tests pass total
(`venv\Scripts\python.exe -m pytest tests/ -v`).

## What's built beyond the required minimum

`GET /v1/requests/{id}` (full record: the request row + its tool_calls,
step-ordered) and `GET /v1/stats` (route counts, cost, average Jev vs. LLM
time, gate result counts) - both listed as "nice extras" in the spec, both
small enough to include and directly useful for exactly the verification
this part asks for.
