"""Protocol health of a run, cell by cell: what went wrong mechanically, never what the agents did.

For staged runs: after each stage, check that every cell ran cleanly before the next, more expensive
stage starts. Per model and cell (arm, form, false signal, extent, task need, answer format,
documentation) it counts episodes run against those planned, failed episodes not yet recovered,
empty replies, refusals, truncated outputs, replies without a FINAL ANSWER line (or without a
COMPLETENESS line where the format asks for one), turns without token usage, turns served by a model
or host other than the recorded snapshot and pinned host, tool calls that returned an error, and cap
hits. It shows no fetch, correctness or disclosure rate, so reading it cannot steer a decision about
the run.

A cell is flagged when any of these mechanical problems occurs in it, or when more than 10% of its
episodes contain a tool call that returned an error (tool errors are also model behavior, such as an
invented cursor, so a few are expected). Cap hits are reported, not flagged. Exit status 1 if any
cell is flagged.

Usage: uv run fplp health data/raw/main --config configs/runs/main.yaml [--model NAME] [--all]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from fplp.metrics import _episode_files, _read_records, stated_completeness

CELL = ["arm", "signal_form", "conflict", "extent", "task_need", "answer_format", "documented"]
PROBLEMS = ["failed", "empty", "refused", "truncated", "no_final", "no_completeness", "no_usage", "wrong_model",
            "wrong_host"]
TOOL_ERROR_SHARE = 0.10


def _cell(condition: dict) -> dict:
    return {k: "" if condition.get(k) is None else str(condition.get(k)) for k in CELL}


def episode_health(rec: dict, snapshot: str | None = None, host: str | None = None, live: bool = True) -> dict:
    """Mechanical problems of one episode (1/0 each), plus tool errors and cap hits. Scripted models
    report no token usage, so `live=False` skips that check, as the run loop does."""
    turns, text = rec.get("turns", []), rec.get("final_text") or ""
    served = {t.get("served_model") for t in turns} - {None}
    hosts = {str(t.get("served_by")).lower() for t in turns if t.get("served_by")}
    return {
        **_cell(rec["condition"]),
        "failed": 0,
        "empty": int(bool(rec.get("empty_reply"))),
        "refused": int(rec.get("stop_reason") == "refusal"),
        "truncated": int(bool(rec.get("truncated"))),
        "no_final": int("FINAL ANSWER" not in text.upper()),
        "no_completeness": int(rec["condition"].get("answer_format") == "completeness"
                               and stated_completeness(text) is None),
        "no_usage": int(live and any(not t.get("tokens_in") and not t.get("tokens_out") for t in turns)),
        "wrong_model": int(bool(snapshot) and bool(served - {snapshot})),
        "wrong_host": int(bool(host) and any(not h.startswith(host) for h in hosts)),
        "tool_error": int(any(c.get("error") for c in rec.get("calls", []))),
        "hit_cap": int(bool(rec.get("hit_cap"))),
    }


def _failures(raw: Path, model: str, done: set[str]) -> dict[str, dict]:
    """Failed episodes not recovered by a later attempt, by episode id, with their condition."""
    path = raw / f"{model}.errors.jsonl"
    failed: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("episode_id") and e["episode_id"] not in done and e.get("condition"):
                failed[e["episode_id"]] = e["condition"]
    return failed


def health_table(raw: Path, models: list[str], registry: dict, plan: dict[str, dict[str, dict]] | None = None
                 ) -> pd.DataFrame:
    """One row per model and cell: planned and run episodes, and the count of each problem."""
    from fplp.run import _pinned_host

    records, _ = _read_records(_episode_files([str(raw)]))
    rows = []
    for model in models:
        cfg = registry.get(model, {})
        seen: set[str] = set()
        for rec in records:
            if rec.get("model") != model or rec["episode_id"] in seen:
                continue
            if plan is not None and rec["episode_id"] not in plan.get(model, {}):
                continue
            seen.add(rec["episode_id"])
            live = cfg.get("provider") != "scripted"
            rows.append({"model": model, "run": 1,
                         **episode_health(rec, cfg.get("snapshot"), _pinned_host(cfg), live)})
        rows += [{"model": model, "run": 0, **_cell(condition), **dict.fromkeys(PROBLEMS, 0), "failed": 1,
                  "tool_error": 0, "hit_cap": 0} for condition in _failures(raw, model, seen).values()]
    counts = ["run", *PROBLEMS, "tool_error", "hit_cap"]
    table = (pd.DataFrame(rows, columns=["model", *CELL, *counts]).groupby(["model", *CELL], dropna=False)[counts]
             .sum().reset_index())
    if plan is not None:
        planned = pd.DataFrame([{"model": m, **_cell(c)} for m, ids in plan.items() if m in models for c in ids.values()])
        planned = planned.groupby(["model", *CELL]).size().rename("planned").reset_index()
        table = planned.merge(table, on=["model", *CELL], how="left").fillna(dict.fromkeys(counts, 0))
        table[counts] = table[counts].astype(int)
    too_many_errors = table["tool_error"] > TOOL_ERROR_SHARE * table["run"].clip(lower=1)
    table["flagged"] = (table[PROBLEMS].sum(axis=1) > 0) | too_many_errors
    return table


def _plan_cells(config: str, models_file: str, models: list[str]) -> dict[str, dict[str, dict]]:
    from fplp.conditions import DEFAULT_MAX_TOOL_CALLS, build_conditions, planned
    from fplp.config import load_models, load_run_config

    cfg = load_run_config(config, require_items=True)
    registry = load_models(models_file)
    conditions = build_conditions(cfg)
    max_calls = cfg.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
    return {m: {eid: c.to_dict() for eid, c in planned(registry[m], conditions, max_calls)} for m in models}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw_dir", help="a run's log directory, e.g. data/raw/main")
    parser.add_argument("--config", help="the run config, to count planned episodes per cell")
    parser.add_argument("--model", action="append", help="limit to these models (repeatable)")
    parser.add_argument("--models-file", default="configs/models.yaml")
    parser.add_argument("--all", action="store_true", help="print every cell, not only flagged ones")
    args = parser.parse_args(argv)

    from fplp.config import load_models, load_run_config

    registry = load_models(args.models_file)
    raw = Path(args.raw_dir)
    models = args.model or (load_run_config(args.config).get("models") if args.config else None) or sorted(
        {p.name.split(".")[0] for p in raw.glob("*.jsonl") if ".errors." not in p.name})
    plan = _plan_cells(args.config, args.models_file, models) if args.config else None
    table = health_table(raw, models, registry, plan)

    for model, g in table.groupby("model", sort=False):
        run = int(g["run"].sum())
        planned = f" of {int(g['planned'].sum())} planned" if "planned" in g else ""
        problems = ", ".join(f"{p} {int(g[p].sum())}" for p in PROBLEMS if g[p].sum()) or "none"
        print(f"{model}: {run} episodes{planned}; problems: {problems}; tool errors in {int(g['tool_error'].sum())} "
              f"episode(s); cap hits {int(g['hit_cap'].sum())}; cells flagged {int(g['flagged'].sum())} of {len(g)}")
    shown = table if args.all else table[table["flagged"]]
    if len(shown):
        with pd.option_context("display.width", 200, "display.max_rows", 500, "display.max_columns", 30):
            print()
            print(shown.drop(columns=["flagged"]).to_string(index=False))
    sys.exit(1 if table["flagged"].any() else 0)


if __name__ == "__main__":
    main()
