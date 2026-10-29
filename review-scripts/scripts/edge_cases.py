"""Fetch edge cases per model, read from the raw episode logs (descriptive; none decides a hypothesis).

Counted for every fetch-rate claim (PENDING.md, section 3, and the 24 Oct readiness memo):
  1. placeholder cursor on the first call: a target call in the first turn carries a cursor, though none
     can have been issued yet (the frozen scoring counts it as a fetch; 24 Oct audit, defect 2);
  2. first-call limit above the page limit: the first target call asked for more rows than the server
     serves, so the full page looks short to the agent (the frozen scoring stores the capped limit, defect 3);
  3. parallel calls: two or more tool calls in one turn (any tool, and on the target query);
  4. no successful target call: no call on the target query returned a page.
Two descriptive categories, post hoc and not pre-registered (asked for on 24 Oct after seeing Mistral's and
Claude's first transcripts), each listed with its turn, the condition and its outcome (error, rows, empty):
  5. invented values: a cursor the server never issued, which it rejected. Cursors appear only in the page
     outputs of the cursor forms (`next_cursor`, `endCursor`, a Link header's `cursor=`), so a cursor is
     invented unless the agent had already read it in an earlier turn's output; row values such as order ids
     are not issued cursors.
  6. re-checks after an end signal: a parameter the tool's schema offers (`page` in every condition; `offset`
     in none) used for a later page after the last page the agent had read signalled the end, split by
     whether that end signal was true or false, and by whether rows came back. Schema-offered parameters
     never count as invented; paging after a page that said more rows exist, or after a page with no signal
     (the none form), is in neither category.
`offset` is in no condition's schema; any use of it is counted beside the categories as a schema check.

  uv run python scripts/edge_cases.py data/raw/main --config configs/runs/main.yaml --cutoff 2026-10-25T17:00:00-04:00 \
      --out results/tables/main_edge_cases.csv --calls-out results/tables/main_continuation_calls.csv \
      --rates-out results/tables/main_post_hoc_rates.csv

Episodes are selected as `fplp score` selects them (planned episodes, duplicates dropped, the cutoff).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from urllib.parse import unquote

import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from fplp.env.tools import tool_schemas
from fplp.metrics import CONDITION_DEFAULTS, _episode_files, _plan, _read_records, select_records

FALSE_END = {"false_end", "false_end_cursor", "false_total", "false_note"}
VISIBLE = {"visible_conflict_total", "visible_conflict_note"}


_CURSOR_KEYS = ("next_cursor", "endCursor")  # the fields that carry a cursor (fplp.signals.render)
_URL_CURSOR = re.compile(r"[?&]cursor=([^&>\"'\s]+)")  # the Link header's next URL
_FIELD_CURSOR = re.compile(r"\"(?:next_cursor|endCursor)\"\s*:\s*\"([^\"]+)\"")


def issued_cursors(output: str) -> set[str]:
    """Cursor values a page output displayed: never an order id or other value in the rows."""
    found: set[str] = set()

    def walk(o) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _CURSOR_KEYS and isinstance(v, str):
                    found.add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    try:
        walk(json.loads(output))
    except (json.JSONDecodeError, TypeError):
        found.update(_FIELD_CURSOR.findall(output or ""))
    found.update(unquote(m) for m in _URL_CURSOR.findall(output or ""))
    return found


def _page(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _shown(c: dict, prev: dict | None, n_items: int) -> str:
    """What the last page the agent had read before this call showed about more rows."""
    if prev is None:
        return "no page read yet"
    remain = prev["offset"] + prev["n_rows"] < n_items
    if prev["offset"] == 0 and c.get("conflict") in VISIBLE:
        return "end (false, contradicted on the page)"
    if prev["offset"] == 0 and c.get("conflict") in FALSE_END:
        return "end (false)"
    if prev["offset"] == 0 and c.get("conflict") == "false_more":
        return "more (false)"
    if c["signal_form"] == "none":
        return "no signal, rows remained" if remain else "no signal, no rows remained"
    return "more" if remain else "end"


def episode_edges(rec: dict) -> tuple[dict, list[dict]]:
    c = {**CONDITION_DEFAULTS, **rec["condition"]}
    calls = rec["calls"]
    target = [x for x in calls if x["is_target"]]
    turns = [x.get("turn") for x in calls]
    known = all(t is not None for t in turns)
    t0 = min((x["turn"] for x in target if x.get("turn") is not None), default=None)
    first = target[0] if target else None
    limit = _page(first["arguments"].get("limit")) if first else None
    per_turn = Counter(turns) if known else Counter()
    target_turn = Counter(x.get("turn") for x in target) if known else Counter()
    edges = {
        "placeholder_cursor_first_turn": int(t0 is not None and any(x.get("turn") == t0 and x["arguments"].get("cursor")
                                                                    for x in target)),
        "first_limit_above_page_limit": int(limit is not None and limit > (c.get("page_limit") or 20)),
        "parallel_calls": int(any(n > 1 for n in per_turn.values())) if known else None,
        "parallel_target_calls": int(any(n > 1 for n in target_turn.values())) if known else None,
        "no_successful_target_call": int(not any(x["error"] is None and x["offset"] is not None for x in target)),
    }
    offered = _offered(c, target[0]["tool"]) if target else set()
    edges["offset_outside_schema"] = sum("offset" in x["arguments"] and "offset" not in offered for x in target)
    listed = []
    for i, x in enumerate(target):
        args, turn = x["arguments"], x.get("turn")
        earlier = [y for j, y in enumerate(target) if (y.get("turn") < turn if known else j < i)]
        read = set().union(*(issued_cursors(y["output"]) for y in calls
                             if y.get("turn") is not None and turn is not None and y["turn"] < turn))
        prev = max((y for y in earlier if y["error"] is None and y["offset"] is not None),
                   key=lambda y: (y.get("turn") or 0, y["offset"]), default=None)
        shown = _shown(c, prev, rec["n_items"])
        found = []
        if args.get("cursor") and str(args["cursor"]) not in read and x["error"]:
            found.append(("invented value", "cursor", args["cursor"]))
        for param, first_value in (("page", 1), ("offset", 0)):
            value = _page(args.get(param))
            if param in offered and value is not None and value > first_value and shown.startswith("end"):
                found.append(("re-check after an end signal", param, args[param]))
        for category, kind, value in found:
            listed.append({
                "model": rec["model"], "episode_id": rec["episode_id"], "turn": turn, "category": category,
                "argument": kind, "value": str(value),
                "end_signal": ("false" if "false" in shown else "true") if category.startswith("re-check") else None,
                "contradicted_on_page": "contradicted" in shown, "previous_page_showed": shown,
                "arm": c.get("arm"), "signal_form": c["signal_form"], "extent": c["extent"], "conflict": c.get("conflict"),
                "task_need": c.get("task_need"),
                "outcome": f"error: {x['error']}" if x["error"] else ("rows" if x["n_rows"] else "empty"),
                "n_rows": x["n_rows"],
            })
    return edges, listed


def episode_flags(rec: dict) -> dict:
    """One episode's eligibility and outcomes for the rates: whether the agent read a page that showed a true
    or a false end (the denominators), and whether it invented a value or re-checked after each end."""
    c = {**CONDITION_DEFAULTS, **rec["condition"]}
    pages = [x for x in rec["calls"] if x["is_target"] and x["error"] is None and x["offset"] is not None]
    shown = [_shown(c, p, rec["n_items"]) for p in pages]
    listed = episode_edges(rec)[1]
    recheck = [x for x in listed if x["category"] == "re-check after an end signal"]
    out = {"model": rec["model"], "arm": c.get("arm"), "signal_form": c["signal_form"], "extent": c["extent"],
           "conflict": c.get("conflict") or "-", "task_need": c.get("task_need"),
           "saw_true_end": any(s == "end" for s in shown), "saw_false_end": any(s.startswith("end (false") for s in shown),
           "invented": any(x["category"] == "invented value" for x in listed)}
    for truth in ("true", "false"):
        out[f"recheck_{truth}"] = any(x["end_signal"] == truth for x in recheck)
        out[f"recheck_{truth}_rows"] = any(x["end_signal"] == truth and x["outcome"] == "rows" for x in recheck)
    return out


def _rate(k: int, n: int) -> dict:
    lo, hi = proportion_confint(k, n, method="wilson") if n else (float("nan"), float("nan"))
    return {"k": k, "n": n, "rate": k / n if n else float("nan"), "lo": lo, "hi": hi}


def rates(records: list[dict]) -> pd.DataFrame:
    """The two post hoc categories as rates with their denominators, per model and condition, and pooled per
    model ("all"): invented values over every episode; re-checks (and re-checks that returned rows) after a
    true or a false end over the episodes in which the agent read a page showing that end. Wilson 95% CIs.
    Rows with no eligible episode (no page in that condition showed that end) are left out: the rate is
    undefined there by design, for example a false end outside the conflict cells."""
    flags = pd.DataFrame([episode_flags(r) for r in records])
    keys = ["arm", "signal_form", "extent", "conflict", "task_need"]
    rows = []
    for model, d in flags.groupby("model"):
        groups = [*d.groupby(keys, dropna=False), (("all",) * len(keys), d)]
        for key, g in groups:
            cond = dict(zip(keys, key, strict=True))
            base = {"model": model, **cond, "label": "post hoc, descriptive"}
            rows.append({**base, "measure": "invented value", **_rate(int(g["invented"].sum()), len(g))})
            for truth in ("true", "false"):
                eligible = g[g[f"saw_{truth}_end"]]
                if eligible.empty:
                    continue
                for suffix, what in (("", "re-check"), ("_rows", "re-check that returned rows")):
                    rows.append({**base, "measure": f"{what} after a {truth} end",
                                 **_rate(int(eligible[f"recheck_{truth}{suffix}"].sum()), len(eligible))})
    return pd.DataFrame(rows)


def _offered(c: dict, tool: str) -> set[str]:
    """Parameters the condition's schema offers for this tool, as the episode built it (fplp.episode)."""
    schemas = tool_schemas(c.get("page_limit") or 20, c.get("documented", True), c["limit_stated"], c["doc_wording"])
    return next((set(t["parameters"]["properties"]) for t in schemas if t["name"] == tool), set())


COLUMNS = ["model", "episode_id", "turn", "category", "argument", "value", "end_signal", "contradicted_on_page",
           "previous_page_showed", "arm", "signal_form", "extent", "conflict", "task_need", "outcome", "n_rows"]


def summarize(records: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    per_episode, calls = [], []
    for rec in records:
        edges, listed = episode_edges(rec)
        per_episode.append({"model": rec["model"], **edges,
                            "invented": sum(x["category"] == "invented value" for x in listed)})
        calls += listed
    eps = pd.DataFrame(per_episode)
    inv = pd.DataFrame(calls, columns=COLUMNS)
    rows = []
    for model, g in eps.groupby("model"):
        i = inv[inv["model"] == model]
        invented, recheck = i[i["category"] == "invented value"], i[i["category"] == "re-check after an end signal"]
        row = {
            "model": model, "episodes": len(g),
            **{k: int(g[k].sum()) for k in ["placeholder_cursor_first_turn", "first_limit_above_page_limit",
                                           "no_successful_target_call"]},
            "parallel_calls": int(g["parallel_calls"].sum()) if g["parallel_calls"].notna().all() else None,
            "parallel_target_calls": int(g["parallel_target_calls"].sum()) if g["parallel_target_calls"].notna().all() else None,
            "post_hoc_invented_values": len(invented),
            "post_hoc_invented_values_episodes": int((g["invented"] > 0).sum()),
        }
        for truth in ("true", "false"):
            r = recheck[recheck["end_signal"] == truth]
            row |= {f"post_hoc_rechecks_after_{truth}_end": len(r),
                    f"post_hoc_rechecks_after_{truth}_end_rows": int((r["outcome"] == "rows").sum()),
                    f"post_hoc_rechecks_after_{truth}_end_empty": int((r["outcome"] == "empty").sum()),
                    f"post_hoc_rechecks_after_{truth}_end_errored": int(r["outcome"].str.startswith("error").sum())}
        row["offset_outside_schema"] = int(g["offset_outside_schema"].sum())
        rows.append(row)
    return pd.DataFrame(rows), inv


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+")
    p.add_argument("--config", help="keep only this run config's planned episodes, as fplp score --config does")
    p.add_argument("--models-file", default="configs/models.yaml")
    p.add_argument("--cutoff", type=datetime.fromisoformat, help="as fplp score --cutoff")
    p.add_argument("--out", help="CSV of the per-model counts")
    p.add_argument("--calls-out", help="CSV of every call in the two post hoc categories")
    p.add_argument("--rates-out", help="CSV of the two post hoc categories as rates with denominators, per model and condition")
    args = p.parse_args(argv)
    records, _ = _read_records(_episode_files(args.inputs))
    records, report = select_records(records, _plan(args.config, args.models_file) if args.config else None,
                                     cutoff=args.cutoff)
    for line in report:
        print(line)
    table, inv = summarize(records)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(table.to_string(index=False))
        if len(inv):
            print("\nPost hoc categories, by model, category, argument, end signal (re-checks), outcome:")
            outcome = inv["outcome"].where(~inv["outcome"].str.startswith("error"), "error")
            print(inv.assign(outcome=outcome, end_signal=inv["end_signal"].fillna("-"))
                  .groupby(["model", "category", "argument", "end_signal", "outcome"]).size().rename("calls").to_string())
    if args.out:
        table.to_csv(args.out, index=False)
    if args.calls_out:
        inv.to_csv(args.calls_out, index=False)
    if args.rates_out:
        rates(records).to_csv(args.rates_out, index=False)
        print(f"wrote the post hoc rates with denominators -> {args.rates_out}")


if __name__ == "__main__":
    main()
