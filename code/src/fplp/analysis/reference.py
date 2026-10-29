"""How a model compares with simple reference agents on the same items: one that follows the hint
(scripted-signal), one that only counts rows (scripted-if-full), and one that follows the hint when there
is one and counts rows otherwise (scripted-hybrid). Descriptive: where a model departs from what a
simple rule would do is where its behavior is not "obvious".

The reference agents run on the same config, seed and items as the model (configs/runs/reference.yaml
mirrors main.yaml), for free. Each row is a cell of needs-all tasks in the final-line format; fetch rates
in percent.

Usage: uv run fplp reference data/processed/main.csv data/processed/reference.csv --model gpt-oss-120b
"""

from __future__ import annotations

import argparse

import pandas as pd

from fplp.analysis.common import analysis_sample

REFERENCES = {"scripted-signal": "follows the hint", "scripted-if-full": "counts rows",
              "scripted-hybrid": "hint, else count"}
MAIN = ["has_more", "next_cursor", "total_count", "nl_note_json", "cursor_plus_note"]
# (label, arm, conflict, forms, extent)
CELLS = [
    ("no hint, more rows behind a full page", "core", None, ["none"], "more_full"),
    ("no hint, full page that is the last", "core", None, ["none"], "last_full"),
    ("no hint, short page with more behind it", "core", None, ["none"], "more_short"),
    ("has_more, more rows exist", "core", None, ["has_more"], "more_full"),
    ("has_more: false, real last page", "core", None, ["has_more"], "last_full"),
    ("null cursor, real last page", "core", None, ["next_cursor"], "last_full"),
    ("total_count = rows shown, real last page", "core", None, ["total_count"], "last_full"),
    ("JSON note, real last page", "core", None, ["nl_note_json"], "last_full"),
    ("any main hint, short page with more behind it", "core", None, MAIN, "more_short"),
    ("wrong has_more: false, more rows exist", "conflict", "false_end", ["has_more"], "more_full"),
    ("wrong total = rows shown, more rows exist", "conflict", "false_total", ["total_count"], "more_full"),
    ("has_more: false beside a total of 87", "conflict", "visible_conflict_total", ["has_more"], "more_full"),
]


def table(model_df: pd.DataFrame, ref_df: pd.DataFrame, model: str) -> pd.DataFrame:
    d = analysis_sample(pd.concat([model_df[model_df.model == model], ref_df[ref_df.model.isin(REFERENCES)]]))
    d = d[(d["task_need"] == "needs_all") & (d["answer_format"] == "final_line") & (d["settled_on_page1"] == 0)]
    conflict = d["conflict"].fillna("").astype(str)
    rows = []
    for label, arm, cf, forms, extent in CELLS:
        cell = d[(d["arm"] == arm) & (conflict == (cf or "")) & d.signal_form.isin(forms) & (d["extent"] == extent)]
        rates = cell.groupby("model")["follow_up"].mean() * 100
        rows.append({"cell": label, model: rates.get(model), **{v: rates.get(k) for k, v in REFERENCES.items()},
                     "n": int((cell.model == model).sum())})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv", help="the model's scored CSV")
    parser.add_argument("reference_csv", help="the reference agents' scored CSV, same config and seed")
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", help="optional CSV")
    args = parser.parse_args(argv)
    t = table(pd.read_csv(args.scored_csv), pd.read_csv(args.reference_csv), args.model)
    with pd.option_context("display.width", 200):
        print(t.round(0).to_string(index=False))
    if args.out:
        t.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
