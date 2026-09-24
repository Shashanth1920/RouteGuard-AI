"""The hospital's record book. 2 tables: one row per request (Book 1), one
row per tool call within that request (Book 2) - a request can have many
tool calls, the same way one patient can get many prescriptions.

Key rule: logging must never break the app. Safety fails closed (when in
doubt, block); logging fails open (when in doubt, keep working and just
warn) - they're different kinds of failure with different costs. A missed
log row is an inconvenience later; a request that fails to answer because
the record book was unavailable is a much bigger problem for no good
reason. Every function here catches its own errors and never raises."""
import json

import psycopg2
import psycopg2.extras

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, LOG_OUTPUT_MAX_CHARS

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id UUID PRIMARY KEY,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    intent TEXT,
    intent_confidence DOUBLE PRECISION,
    complexity_score DOUBLE PRECISION,
    complexity_label TEXT,
    risk DOUBLE PRECISION,
    needs_tool DOUBLE PRECISION,
    is_fallback BOOLEAN,

    route TEXT,
    rule INTEGER,
    reason TEXT,
    status TEXT,

    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost DOUBLE PRECISION,

    jev_time DOUBLE PRECISION,
    llm_time DOUBLE PRECISION,
    total_time DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    tool TEXT NOT NULL,
    arguments JSONB,
    gate_result TEXT,
    gate_reason TEXT,
    gate_destructive_score DOUBLE PRECISION,
    gate_matches_score DOUBLE PRECISION,
    gate_time DOUBLE PRECISION,
    executed BOOLEAN NOT NULL,
    output TEXT
);
"""


def get_connection(db_name: str = None):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=db_name or DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    conn.autocommit = True
    return conn


def init_db(db_name: str = None) -> None:
    """Creates both tables if they don't exist yet. Safe to call every
    startup - CREATE TABLE IF NOT EXISTS is a no-op once they're there."""
    conn = get_connection(db_name)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
    finally:
        conn.close()


def save_request(
    request_id: str, message: str, decision, route_result, answer: dict,
    total_time: float, db_name: str = None,
) -> None:
    """Called once per API request, after the answer is ready. Never
    raises - a database problem must not turn into a failed user request."""
    try:
        conn = get_connection(db_name)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO requests (
                        id, message, intent, intent_confidence, complexity_score,
                        complexity_label, risk, needs_tool, is_fallback,
                        route, rule, reason, status,
                        model_used, input_tokens, output_tokens, cost,
                        jev_time, llm_time, total_time
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        request_id, message, decision.intent, decision.intent_confidence,
                        decision.complexity_score, decision.complexity_label, decision.risk,
                        decision.needs_tool, decision.is_fallback,
                        route_result.route, route_result.rule, route_result.reason,
                        "error" if answer.get("error") else "ok",
                        answer.get("model_used"), answer.get("input_tokens"),
                        answer.get("output_tokens"), answer.get("cost"),
                        decision.time_taken, answer.get("llm_time_taken"), total_time,
                    ),
                )

                tools_used = answer.get("tools_used") or []
                gate_log = answer.get("gate_log") or []
                for step_number, (tool, gate) in enumerate(zip(tools_used, gate_log), start=1):
                    output_text = json.dumps(tool["output"])[:LOG_OUTPUT_MAX_CHARS]
                    cur.execute(
                        """
                        INSERT INTO tool_calls (
                            request_id, step_number, tool, arguments,
                            gate_result, gate_reason, gate_destructive_score,
                            gate_matches_score, gate_time, executed, output
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            request_id, step_number, tool["name"], json.dumps(tool["input"]),
                            gate["result"], gate["reason"], gate.get("destructive_score"),
                            gate.get("matches_score"), gate.get("time_taken"),
                            gate["result"] == "ALLOW", output_text,
                        ),
                    )
        finally:
            conn.close()
    except Exception as e:
        print(f"[routeguard] WARNING: failed to log request {request_id} to the database: {e}")


def get_request(request_id: str, db_name: str = None) -> dict | None:
    """One full record: the request row plus its tool_calls, step-ordered.
    Lets you look up "why did request X go to human review" after the fact
    instead of only being able to watch it live."""
    conn = get_connection(db_name)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM requests WHERE id = %s", (request_id,))
            request_row = cur.fetchone()
            if request_row is None:
                return None
            cur.execute(
                "SELECT * FROM tool_calls WHERE request_id = %s ORDER BY step_number", (request_id,)
            )
            tool_calls = cur.fetchall()
        return {**dict(request_row), "tool_calls": [dict(t) for t in tool_calls]}
    finally:
        conn.close()


def get_stats(db_name: str = None) -> dict:
    """Counts per route, cost/time averages, and how many tool calls the
    gate blocked - the numbers Part 6's "how to verify" checklist asks for,
    computed from real logged data instead of eyeballing a query each time."""
    conn = get_connection(db_name)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT count(*) AS total FROM requests")
            total_requests = cur.fetchone()["total"]

            cur.execute("SELECT route, count(*) AS count FROM requests GROUP BY route ORDER BY route")
            by_route = {row["route"]: row["count"] for row in cur.fetchall()}

            cur.execute("SELECT sum(cost) AS total_cost FROM requests")
            total_cost = cur.fetchone()["total_cost"]

            cur.execute("SELECT avg(jev_time) AS avg_jev_time, avg(llm_time) AS avg_llm_time FROM requests")
            avg_times = dict(cur.fetchone())

            cur.execute(
                "SELECT gate_result, count(*) AS count FROM tool_calls GROUP BY gate_result ORDER BY gate_result"
            )
            gate_results = {row["gate_result"]: row["count"] for row in cur.fetchall()}
        return {
            "total_requests": total_requests,
            "by_route": by_route,
            "total_cost": total_cost,
            "avg_jev_time": avg_times["avg_jev_time"],
            "avg_llm_time": avg_times["avg_llm_time"],
            "tool_calls_by_gate_result": gate_results,
            "tool_calls_blocked": gate_results.get("BLOCK", 0),
        }
    finally:
        conn.close()
