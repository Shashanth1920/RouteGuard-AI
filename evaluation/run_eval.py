"""The inspector. Runs the labeled dataset through the real system and
saves a raw results file per experiment - never recomputes metrics by
re-paying for API calls, since `report` reads only the raw files.

Usage:
    python evaluation/run_eval.py decision --dataset dev
    python evaluation/run_eval.py decision --dataset test
    python evaluation/run_eval.py gate
    python evaluation/run_eval.py full --dataset test --sample 50
    python evaluation/run_eval.py consistency --dataset dev --n 20
    python evaluation/run_eval.py report

decision mode = Jev + router only, no LLM/agent/gate calls - cheap, run
on the whole dataset. full mode = the real end-to-end pipeline
(Jev -> router -> LLM/agent -> gate -> tools) - costs real money and
time, so only a sample. Both call the app's own functions directly
(not over HTTP), and never call save_request() - this is a separate
evaluation artifact, not production traffic.
"""
import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).parent
sys.path.insert(0, str(EVAL_DIR.parent))  # so `app.*` imports work regardless of cwd
RAW_DIR = EVAL_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)

_CUTOFFS = {}  # set once by run_decision() before any worker thread reads it


def _load(dataset: str) -> list:
    return json.loads((EVAL_DIR / f"{dataset}.json").read_text(encoding="utf-8"))


def _settings_snapshot() -> dict:
    from app import config
    return {
        "jev_model": config.JEV_MODEL,
        "small_llm_model": config.SMALL_LLM_MODEL,
        "strong_llm_model": config.STRONG_LLM_MODEL,
        "risk_cutoff": config.RISK_CUTOFF,
        "intent_confidence_cutoff": config.INTENT_CONFIDENCE_CUTOFF,
        "needs_tool_cutoff": config.NEEDS_TOOL_CUTOFF,
        "gate_match_cutoff": config.GATE_MATCH_CUTOFF,
        "gate_risk_cutoff": config.GATE_RISK_CUTOFF,
        "agent_max_steps": config.AGENT_MAX_STEPS,
    }


def _decision_row(row: dict) -> dict:
    from app.decision.jev_classifier import classify
    from app.routing.router import route

    decision = classify(row["message"])
    result = route(decision)
    return {
        **{k: row[k] for k in ("id", "category", "subcategory", "message", "expected", "expected_route")},
        "got": {
            "intent": decision.intent,
            "intent_confidence": decision.intent_confidence,
            "complexity_score": decision.complexity_score,
            "complexity_label": decision.complexity_label,
            "risk": decision.risk,
            "risky": decision.risk >= _CUTOFFS["risk"],
            "needs_tool_score": decision.needs_tool,
            "needs_tool": decision.needs_tool >= _CUTOFFS["needs_tool"],
            "is_fallback": decision.is_fallback,
        },
        "got_route": result.route,
        "got_rule": result.rule,
        "got_reason": result.reason,
        "jev_time": decision.time_taken,
    }


def run_decision(dataset: str, workers: int = 8):
    from app.config import NEEDS_TOOL_CUTOFF, RISK_CUTOFF
    global _CUTOFFS
    _CUTOFFS = {"risk": RISK_CUTOFF, "needs_tool": NEEDS_TOOL_CUTOFF}

    rows = _load(dataset)
    print(f"Running decision mode on {dataset} ({len(rows)} rows, {workers} workers)...")
    results = [None] * len(rows)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_decision_row, row): i for i, row in enumerate(rows)}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            done += 1
            if done % 25 == 0 or done == len(rows):
                print(f"  {done}/{len(rows)}")

    out = {"dataset": dataset, "mode": "decision", "settings": _settings_snapshot(), "rows": results}
    out_path = RAW_DIR / f"decision_{dataset}.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out_path}")


def run_gate():
    from app.safety.gate import check_gate
    cases = json.loads((EVAL_DIR / "gate_cases.json").read_text(encoding="utf-8"))
    print(f"Running {len(cases)} gate cases...")
    results = []
    for case in cases:
        result = check_gate(case["tool"], case["arguments"], case["user_message"], case["destructive_label"])
        results.append({
            **case,
            "got_result": result.result,
            "got_reason": result.reason,
            "destructive_score": result.destructive_score,
            "matches_score": result.matches_score,
            "gate_time": result.time_taken,
            "is_fallback": result.is_fallback,
        })
    out = {"mode": "gate", "settings": _settings_snapshot(), "rows": results}
    out_path = RAW_DIR / "gate.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out_path}")


def _sample_stratified(rows: list, n: int) -> list:
    """Deterministic, category-proportional sample - not random, so it's
    reproducible. Takes evenly-spaced rows within each category's slice."""
    by_category = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)

    total = len(rows)
    sample = []
    for category, group in by_category.items():
        take = max(1, round(n * len(group) / total))
        step = max(1, len(group) // take)
        sample.extend(group[::step][:take])
    return sample[:n]


def run_full(dataset: str, sample: int, ids: str = None, out_name: str = None):
    from app.decision.jev_classifier import classify
    from app.llm.client import get_answer
    from app.routing.router import route
    from app.tools import database

    rows = _load(dataset)
    if ids:
        wanted = set(ids.split(","))
        sampled = [r for r in rows if r["id"] in wanted]
        print(f"Running full mode on {len(sampled)} specific rows from {dataset}: {ids}")
    else:
        sampled = _sample_stratified(rows, sample)
        print(f"Running full mode on {len(sampled)} rows sampled from {dataset}...")

    results = []
    for i, row in enumerate(sampled, start=1):
        database.reset()  # every row starts from the same known fake-DB state
        start = time.monotonic()
        decision = classify(row["message"])
        result = route(decision)
        answer = get_answer(result.route, row["message"], decision.complexity_label)
        total_time = time.monotonic() - start

        unsafe_executed = False
        for gate_entry, tool_call in zip(answer.get("gate_log") or [], answer.get("tools_used") or []):
            if gate_entry["result"] != "ALLOW":
                tool_output = tool_call["output"]
                if isinstance(tool_output, dict) and "error" not in tool_output:
                    unsafe_executed = True

        results.append({
            **{k: row[k] for k in ("id", "category", "subcategory", "message", "expected", "expected_route")},
            "got": {
                "intent": decision.intent, "complexity_label": decision.complexity_label,
                "risk": decision.risk, "needs_tool_score": decision.needs_tool,
                "is_fallback": decision.is_fallback,
            },
            "got_route": result.route,
            "answer": answer.get("answer"),
            "model_used": answer.get("model_used"),
            "error": answer.get("error"),
            "tools_used": answer.get("tools_used"),
            "gate_log": answer.get("gate_log"),
            "steps": answer.get("steps"),
            "unsafe_action_executed": unsafe_executed,
            "input_tokens": answer.get("input_tokens"),
            "output_tokens": answer.get("output_tokens"),
            "cost": answer.get("cost"),
            "jev_time": decision.time_taken,
            "llm_time": answer.get("llm_time_taken"),
            "total_time": total_time,
        })
        print(f"  {i}/{len(sampled)}: {result.route:14s} {row['message'][:50]}")

    database.reset()
    out = {"dataset": dataset, "mode": "full", "settings": _settings_snapshot(), "rows": results}
    out_path = RAW_DIR / (out_name or f"full_{dataset}.json")
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out_path}")


def run_consistency(dataset: str, n: int):
    from app.decision.jev_classifier import classify

    rows = _load(dataset)[:n]
    print(f"Consistency check: running {len(rows)} rows twice...")

    def run_once():
        return [
            {
                "message": r["message"],
                "intent": (d := classify(r["message"])).intent,
                "complexity_label": d.complexity_label,
                "risky": d.risk >= 0.5,
                "needs_tool": d.needs_tool >= 0.4,
            }
            for r in rows
        ]

    run1 = run_once()
    run2 = run_once()

    diffs = []
    for a, b in zip(run1, run2):
        changed = {k: (a[k], b[k]) for k in ("intent", "complexity_label", "risky", "needs_tool") if a[k] != b[k]}
        if changed:
            diffs.append({"message": a["message"], "changed": changed})

    out = {"mode": "consistency", "n": len(rows), "run1": run1, "run2": run2, "diffs": diffs}
    out_path = RAW_DIR / "consistency.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(diffs)}/{len(rows)} rows changed between runs. Saved {out_path}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("decision")
    p.add_argument("--dataset", choices=["dev", "test"], required=True)
    p.add_argument("--workers", type=int, default=8)

    sub.add_parser("gate")

    p = sub.add_parser("full")
    p.add_argument("--dataset", choices=["dev", "test"], required=True)
    p.add_argument("--sample", type=int, default=50)
    p.add_argument("--ids", help="comma-separated row ids to run instead of a stratified sample")
    p.add_argument("--out", help="output filename under evaluation/raw/ (default: full_<dataset>.json)")

    p = sub.add_parser("consistency")
    p.add_argument("--dataset", choices=["dev", "test"], default="dev")
    p.add_argument("--n", type=int, default=20)

    sub.add_parser("report")

    args = parser.parse_args()
    if args.command == "decision":
        run_decision(args.dataset, args.workers)
    elif args.command == "gate":
        run_gate()
    elif args.command == "full":
        run_full(args.dataset, args.sample, args.ids, args.out)
    elif args.command == "consistency":
        run_consistency(args.dataset, args.n)
    elif args.command == "report":
        import build_report
        build_report.main()


if __name__ == "__main__":
    main()
