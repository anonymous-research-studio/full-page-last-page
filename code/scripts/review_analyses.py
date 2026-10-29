"""Exploratory analyses from the review of 23 Oct 2026 (REVIEW-CHECKLIST.md, section 4), per model.

Formed after the interim look at gpt-oss-120b, so every number here is exploratory and labeled post hoc in
the paper. None decides a hypothesis. Kept outside src/ (and uncommitted) while the remaining runs use the
registered commit; commit it after the runs.

  4.1  H6 against the contradicting field shown alone: a false end beside a total (or note) minus the same
       total (or note) alone, on the same items. Equal rates mean the false end adds nothing once the
       contradicting field is there, which fits following that field as well as noticing the contradiction.
  4.3  The no-signal baseline by task (fetching when more rows exist, and on a real last page), and H4 by
       task: fetching and incomplete answers under the false end signals against no signal.
  4.4  Stated completeness (the COMPLETENESS line) by disclosure stratum, on incomplete and complete answers:
       disclosure evidence that needs no flag and no hand label.
  4.5  The exists task where a fetch was needed: correct against justified correct, and (with --raw) the
       gold answer of the correct but unjustified ones.
  4.6  Episodes that paged but stopped before the rows their answer needed, by form.
  4.7  The H4 manipulation check as registered (false end signals minus real last pages, 90% CI), read from
       the `fplp hypotheses` CSV so the paper cites one number.

The cells and exclusions are those of the amended tests (`fplp.analysis.hypotheses._cells`).

Usage: uv run python scripts/review_analyses.py data/processed/main.csv --raw data/raw/main \
           --hypotheses results/tables/main_hypotheses.csv --out results/tables/main_review_analyses.csv
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, paired
from fplp.analysis.hypotheses import FALSE_END, _cells

ROWS: list[dict] = []


def add(section: str, model: str, label: str, n, value, lo=np.nan, hi=np.nan, p=np.nan, note: str = "") -> None:
    ROWS.append({"section": section, "model": model, "label": label, "n": n, "value": value, "lo": lo, "hi": hi,
                 "p": p, "note": note})


def rate(cell: pd.DataFrame, value: str = "follow_up") -> tuple[int, float]:
    return len(cell), float(cell[value].mean()) if len(cell) else np.nan


def h6_against_field_alone(model: str, c: dict, rng) -> None:
    conflicts, need = c["conflicts"], c["need"]
    for visible, alone in [("visible_conflict_total", "total_count"), ("visible_conflict_note", "nl_note_json")]:
        a, b = conflicts[conflicts["conflict"] == visible], need[need.signal_form == alone]
        t = paired(a, b, "follow_up", rng)
        x, y = a.groupby("key")["follow_up"].mean(), b.groupby("key")["follow_up"].mean()
        common = x.index.intersection(y.index)
        up, down = int((x[common] > y[common]).sum()), int((x[common] < y[common]).sum())
        add("4.1", model, f"{visible} - {alone} alone, more rows exist", t["n"], t["diff"], t["lo"], t["hi"], t["p"],
            f"rates {rate(a)[1]:.2f} vs {rate(b)[1]:.2f}; discordant +{up}/-{down}")


def baseline_and_h4_by_task(model: str, c: dict) -> None:
    need, last, conflicts = c["need"], c["last"], c["conflicts"]
    none_more, none_last = need[need.signal_form == "none"], last[last.signal_form == "none"]
    false_ends = conflicts[conflicts["conflict"].isin(list(FALSE_END))]
    for task in sorted(set(need["task_type"])):
        n, r = rate(none_more[none_more.task_type == task])
        add("4.3", model, f"no signal, more rows exist: fetch rate ({task})", n, r)
        n, r = rate(none_last[none_last.task_type == task])
        add("4.3", model, f"no signal, real last page: fetch rate ({task})", n, r)
        fe = false_ends[false_ends.task_type == task]
        nm = none_more[none_more.task_type == task]
        add("4.3", model, f"H4 by task: fetch, no signal - false ends ({task})", len(fe), rate(nm)[1] - rate(fe)[1])
        add("4.3", model, f"H4 by task: incomplete, false ends - no signal ({task})", len(fe),
            float((1 - fe["evidence_seen"]).mean() - (1 - nm["evidence_seen"]).mean()) if len(fe) and len(nm) else np.nan)


def stated_completeness(model: str, d: pd.DataFrame) -> None:
    field = d[(d["answer_format"] == "completeness") & (d["task_need"] == "needs_all")].copy()
    field["stratum"] = field["disclosure_stratum"].fillna("complete answer").astype(str)
    field["stated"] = field["stated_completeness"].fillna("missing").astype(str)
    for (stratum, stated), g in field.groupby(["stratum", "stated"]):
        add("4.4", model, f"COMPLETENESS line '{stated}' ({stratum})", len(g), len(g) / (field["stratum"] == stratum).sum())


def exists_correctness(model: str, d: pd.DataFrame, gold: dict[str, str]) -> None:
    ex = d[(d["task_type"] == "exists") & d["fetch_needed"].astype(bool)]
    add("4.5", model, "exists, fetch needed: correct", len(ex), float(ex["correct"].mean()) if len(ex) else np.nan)
    add("4.5", model, "exists, fetch needed: justified correct", len(ex),
        float(ex["justified_correct"].mean()) if len(ex) else np.nan)
    lucky = ex[(ex["correct"] == 1) & (ex["justified_correct"] == 0)]
    if gold:
        answers = lucky["episode_id"].map(gold).value_counts().to_dict()
        add("4.5", model, "correct but unjustified, by gold answer", len(lucky), np.nan, note=str(answers))


def stopped_short(model: str, c: dict) -> None:
    core = c["core"]
    followed = core[(core["task_need"] == "needs_all") & core["fetch_needed"].astype(bool) & (core["follow_up"] == 1)]
    for form, g in followed.groupby("signal_form"):
        add("4.6", model, f"paged, then had the rows the answer needs ({form})", len(g), float(g["evidence_seen"].mean()),
            note=f"retrieved every row: {g['completion'].mean():.2f}")


def manipulation_check(hypotheses_csv: str | None) -> None:
    if not hypotheses_csv:
        return
    h = pd.read_csv(hypotheses_csv)
    rows = h[(h["family"] == "registered") & (h["hypothesis"] == "H4") & (h["part"] == "manipulation check")]
    for _, r in rows.iterrows():
        add("4.7", r["model"], r["test"], r["n"], r["diff"], r["lo"], r["hi"], r["p"], "as registered (90% CI)")


def gold_answers(raw: str | None) -> dict[str, str]:
    """Episode id -> gold answer for the exists task, from the episode logs."""
    if not raw:
        return {}
    out = {}
    for path in sorted(Path(raw).glob("*.jsonl*")):
        if ".errors." in path.name:
            continue
        with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    if rec["condition"]["task_type"] == "exists":
                        out[rec["episode_id"]] = str(rec["gold"]["value"])
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv")
    parser.add_argument("--raw", help="episode logs, for the gold answers in 4.5")
    parser.add_argument("--hypotheses", help="the `fplp hypotheses` CSV, for 4.7")
    parser.add_argument("--out", help="optional CSV")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    rng = np.random.default_rng(args.seed)
    d = analysis_sample(pd.read_csv(args.scored_csv))
    gold = gold_answers(args.raw)
    for model, g in d.groupby("model"):
        c = _cells(g, own_small_page=True)
        h6_against_field_alone(model, c, rng)
        baseline_and_h4_by_task(model, c)
        stated_completeness(model, g)
        exists_correctness(model, g, gold)
        stopped_short(model, c)
    manipulation_check(args.hypotheses)
    table = pd.DataFrame(ROWS)
    with pd.option_context("display.width", 220, "display.max_rows", 500, "display.max_colwidth", 70):
        print(table.round(3).to_string(index=False))
    if args.out:
        table.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
