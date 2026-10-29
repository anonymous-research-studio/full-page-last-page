"""Direct contrasts between signal forms on a real full last page, with 95% intervals (descriptive).

PENDING.md (section 3) asks for them beside each form's contrast with no signal: the registered and
amended H2a compare every main form only with no signal past a full last page ("none - X, fetch past a
full last page"), and the only form-against-form contrasts registered or amended (H1b, H2b: the JSON note
against total_count, the cursor plus note against the cursor) are on other cells. Every pair of main
forms is computed here on the amended H2a cell (`fplp.analysis.hypotheses._cells`, own small pages left
out), paired by item (`fplp.analysis.common.paired`). Each row is labelled by looking the same contrast
up in the `fplp hypotheses` CSV: "pre-registered" or "amended" if that family has it on this cell, "post
hoc" otherwise. Holm across the pairs per model is given as a descriptive aid, not a test.

  uv run python scripts/form_contrasts.py data/processed/main.csv --hypotheses results/tables/main_hypotheses.csv \
      --out results/tables/main_form_contrasts.csv
"""

from __future__ import annotations

import argparse
from itertools import combinations

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, holm, paired
from fplp.analysis.hypotheses import MAIN_EXPLICIT, _cells

CELL = "fetch past a full last page"
FAMILY_LABEL = {"registered": "pre-registered", "amended": "amended"}


def label(a: str, b: str, hypotheses: pd.DataFrame | None) -> str:
    if hypotheses is None:
        return "post hoc"
    for test in (f"{a} - {b}, {CELL}", f"{b} - {a}, {CELL}"):
        families = set(hypotheses.loc[hypotheses["test"].str.startswith(test), "family"])
        for family in ("registered", "amended"):
            if family in families:
                return FAMILY_LABEL[family]
    return "post hoc"


def contrasts(scored: pd.DataFrame, hypotheses: pd.DataFrame | None = None, seed: int = 0,
              n_boot: int = 2000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for model, d in analysis_sample(scored).groupby("model"):
        last = _cells(d, own_small_page=True)["last"]
        tests = []
        for a, b in combinations(MAIN_EXPLICIT, 2):
            t = paired(last[last.signal_form == a], last[last.signal_form == b], "follow_up", rng, n_boot=n_boot)
            tests.append({"model": model, "contrast": f"{a} - {b}, {CELL}", **t, "label": label(a, b, hypotheses),
                          "rate_a": last.loc[last.signal_form == a, "follow_up"].mean(),
                          "rate_b": last.loc[last.signal_form == b, "follow_up"].mean()})
        for t, s in zip(tests, holm([t["p"] for t in tests]), strict=True):
            t["holm_descriptive"] = s
        rows += tests
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scored_csv")
    p.add_argument("--hypotheses", help="the fplp hypotheses CSV, to label each contrast by family")
    p.add_argument("--out")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-boot", type=int, default=2000)
    args = p.parse_args(argv)
    hyp = pd.read_csv(args.hypotheses) if args.hypotheses else None
    table = contrasts(pd.read_csv(args.scored_csv), hyp, args.seed, args.n_boot)
    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(table[["model", "contrast", "n", "diff", "lo", "hi", "p", "label"]].round(3).to_string(index=False))
    if args.out:
        table.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
