"""The frozen scoring against the second scoring (`fplp score --fixes`), per model.

The 24 Oct code audit found three latent scoring defects, none affecting gpt-oss-120b's episodes;
PENDING.md (section 3) fixes them after the runs, reports both scorings, and records the change as a
deviation. This reports, per model, how many episodes each fix changes and, given both scorings'
`fplp hypotheses` CSVs, every test whose verdict, estimability or estimate moves.

  uv run fplp score data/raw/main --config configs/runs/main.yaml --cutoff ... --out frozen.csv
  uv run fplp score data/raw/main --config configs/runs/main.yaml --cutoff ... --fixes --out fixed.csv
  uv run python scripts/compare_scorings.py frozen.csv fixed.csv [--hypotheses frozen_h.csv fixed_h.csv]

`--exclude-asked-above OUT` also writes the fixed scoring without episodes whose first call asked for
more rows than the page limit (defect 3), for a sensitivity run of `fplp hypotheses`.
"""

from __future__ import annotations

import argparse

import pandas as pd

FETCH = ["follow_up", "responsive_follow_up", "followup_calls", "speculative_fetch", "missed_fetch", "extra_fetch"]


def _changed(g: pd.DataFrame, col: str) -> int:
    return int((g[col].fillna(-1).astype(str) != g[f"{col}_fix"].fillna(-1).astype(str)).sum())


def episodes(frozen: pd.DataFrame, fixed: pd.DataFrame) -> pd.DataFrame:
    m = frozen.merge(fixed, on=["episode_id", "model"], suffixes=("", "_fix"), validate="one_to_one")
    rows = []
    for model, g in m.groupby("model"):
        incomplete = g[(g["task_need"] == "needs_all") & (g["evidence_seen"] == 0)]
        moved = incomplete[incomplete["disclosure_stratum"].fillna("") != incomplete["disclosure_stratum_fix"].fillna("")]
        rows.append({
            "model": model, "episodes": len(g),
            **{f"{c}_changed": _changed(g, c) for c in FETCH},
            "stratum_changed": len(moved),
            "stratum_moves": "; ".join(f"{a}->{b}: {n}" for (a, b), n in
                                       moved.groupby(["disclosure_stratum", "disclosure_stratum_fix"], dropna=False).size().items()),
            "incomplete_outside_more_extents": int((~incomplete["extent"].isin(["more_full", "more_short"])).sum()),
            # descriptive and post hoc: labels outside Amendment 1's strata, mapped back in disclosure_stratum
            "post_hoc_no_page_served": int((g["stratum_post_hoc"] == "no_page_served").sum()),
            "post_hoc_end_shown": int((g["stratum_post_hoc"] == "end_shown").sum()),
            "no_target_page": int(g["no_target_page"].sum()),
            "asked_above_limit": int(g["asked_above_limit"].sum()),
        })
    return pd.DataFrame(rows)


def hypotheses(frozen: str, fixed: str) -> pd.DataFrame:
    keys = ["model", "family", "hypothesis", "part", "test"]
    a, b = pd.read_csv(frozen), pd.read_csv(fixed)
    m = a.merge(b, on=keys, how="outer", suffixes=("", "_fix"), indicator=True)

    def same(col: str, numeric: bool = False) -> pd.Series:
        x, y = m[col], m[f"{col}_fix"]
        both_missing = x.isna() & y.isna()
        if numeric:
            return both_missing | ((x - y).abs() <= 1e-9).fillna(False)
        return both_missing | (x.astype(object) == y.astype(object)).fillna(False)

    differs = (m["_merge"] != "both") | ~same("supported") | ~same("estimable") | ~same("diff", True) | ~same("n", True)
    return m.loc[differs, [*keys, "n", "n_fix", "diff", "diff_fix", "supported", "supported_fix", "estimable", "estimable_fix"]]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("frozen_csv")
    p.add_argument("fixed_csv")
    p.add_argument("--hypotheses", nargs=2, metavar=("FROZEN_H", "FIXED_H"))
    p.add_argument("--out", help="CSV of the per-model episode counts")
    p.add_argument("--exclude-asked-above", metavar="OUT")
    args = p.parse_args(argv)
    frozen, fixed = pd.read_csv(args.frozen_csv), pd.read_csv(args.fixed_csv)
    table = episodes(frozen, fixed)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 80):
        print(table.to_string(index=False))
        if args.hypotheses:
            h = hypotheses(*args.hypotheses)
            print(f"\n{len(h)} test row(s) differ between the scorings" + (":" if len(h) else ""))
            if len(h):
                print(h.to_string(index=False))
    if args.out:
        table.to_csv(args.out, index=False)
    if args.exclude_asked_above:
        kept = fixed[fixed["asked_above_limit"] == 0]
        kept.to_csv(args.exclude_asked_above, index=False)
        print(f"\nwrote {len(kept)} of {len(fixed)} episodes (without first calls above the page limit) to {args.exclude_asked_above}")


if __name__ == "__main__":
    main()
