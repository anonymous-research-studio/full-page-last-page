"""Amendment 2's exploratory checks, computed exactly as pre-specified there. They decide no hypothesis.

C1 (wording): with pagination documented, does "when it includes one" act as an end cue? Fetching
   under the plain wording (without the clause) minus the default wording, same form, extent and items:
   C1a no signal, more rows exist; C1b no signal, real last page; C1c-f has_more and the JSON note on
   both extents (descriptive).
C2 (total name): does a total equal to the rows shown read as "done" when the field is unambiguously
   named? Fetching under total_matches minus total_count, same items: C2a on a real last page (negative
   means the unambiguous name reads more as "done"); C2b when more rows exist.

Needs-all tasks; exists items settled on page 1 and episodes whose first call asked for fewer rows than
the page limit are left out, as in the amended tests. Paired by item, 95% intervals.

Usage: uv run fplp robustness data/processed/robustness.csv --out results/tables/robustness.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, paired

CHECKS = [
    ("C1a", "no signal, more rows exist: plain - default wording", ("doc", "none", "more_full")),
    ("C1b", "no signal, real last page: plain - default wording", ("doc", "none", "last_full")),
    ("C1c", "has_more, more rows exist: plain - default wording", ("doc", "has_more", "more_full")),
    ("C1d", "has_more, real last page: plain - default wording", ("doc", "has_more", "last_full")),
    ("C1e", "JSON note, more rows exist: plain - default wording", ("doc", "nl_note_json", "more_full")),
    ("C1f", "JSON note, real last page: plain - default wording", ("doc", "nl_note_json", "last_full")),
    ("C2a", "real last page: total_matches - total_count", ("total", None, "last_full")),
    ("C2b", "more rows exist: total_matches - total_count", ("total", None, "more_full")),
]


def run(df: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = analysis_sample(df)
    d = d[(d["settled_on_page1"] == 0) & (d["own_small_page"] == 0) & (d["task_need"] == "needs_all")
          & (d["answer_format"] == "final_line")]
    wording = d["doc_wording"].fillna("default").astype(str) if "doc_wording" in d else pd.Series("default", d.index)
    rows = []
    for label, test, (kind, form, extent) in CHECKS:
        cell = d[d["extent"] == extent]
        if kind == "doc":
            a = cell[(cell.signal_form == form) & (wording[cell.index] == "plain")]
            b = cell[(cell.signal_form == form) & (wording[cell.index] == "default")]
        else:
            a, b = cell[cell.signal_form == "total_matches"], cell[cell.signal_form == "total_count"]
        for model in sorted(set(a["model"]) | set(b["model"])):
            am, bm = a[a.model == model], b[b.model == model]
            rows.append({"model": model, "check": label, "test": test, "rate_a": am["follow_up"].mean(),
                         "rate_b": bm["follow_up"].mean(), **paired(am, bm, "follow_up", rng, n_boot=n_boot)})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv")
    parser.add_argument("--out", help="optional CSV of the checks")
    parser.add_argument("--n-boot", type=int, default=2000)
    args = parser.parse_args(argv)
    table = run(pd.read_csv(args.scored_csv), n_boot=args.n_boot)
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(table.drop(columns=["method"], errors="ignore").round(3).to_string(index=False))
    if args.out:
        table.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
