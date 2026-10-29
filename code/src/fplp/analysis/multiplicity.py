"""A sensitivity analysis added by amendment 2 (after the interim look): one correction across every
main contrast of the amended family, per model, instead of Holm within each hypothesis part. It changes
no verdict; it shows which contrasts would survive a stricter rule. Holm (family-wise) and
Benjamini-Hochberg (false discovery rate) at .05. Tests decided by a bound instead of a p value (H3a,
H3b, H5a, H5b's informativeness part) are not included.

Usage: uv run fplp multiplicity results/tables/main_hypotheses.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from fplp.analysis.common import holm

# (hypothesis, part) rows that carry the confirmatory contrasts, each predicted positive.
PRIMARY = {("A1", "a"), ("H1", "a"), ("H1", "b (information-matched)"), ("H2", "a"), ("H2b", "a"),
           ("H3", "control: full vs short last page"), ("H4", "a"), ("H5b", "a"), ("H6", "a"), ("A1u", "a"),
           ("H1u", "a"), ("H2u", "a")}


def benjamini_hochberg(p: list[float], q: float = 0.05) -> list[bool]:
    p = np.nan_to_num(np.asarray(p, dtype=float), nan=1.0)
    order = np.argsort(p)
    passed = p[order] <= q * np.arange(1, len(p) + 1) / len(p)
    k = passed.nonzero()[0].max() + 1 if passed.any() else 0
    out = np.zeros(len(p), dtype=bool)
    out[order[:k]] = True
    return out.tolist()


def run(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail[(detail.family == "amended") & detail.apply(lambda r: (r.hypothesis, r.part) in PRIMARY, axis=1)
               & detail["p"].notna()].copy()
    frames = []
    for _, g in d.groupby("model"):
        g = g.copy()
        g["holm_all"] = [bool(s and x > 0) for s, x in zip(holm(g["p"].tolist()), g["diff"], strict=True)]
        g["bh_all"] = [bool(s and x > 0) for s, x in zip(benjamini_hochberg(g["p"].tolist()), g["diff"], strict=True)]
        g["within_part"] = g["supported"].map(lambda v: v is True or v == "True" or v == 1.0)
        frames.append(g)
    return pd.concat(frames)[["model", "hypothesis", "part", "test", "diff", "p", "within_part", "holm_all", "bh_all"]] \
        if frames else pd.DataFrame()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hypotheses_csv")
    parser.add_argument("--out", help="optional CSV")
    args = parser.parse_args(argv)
    t = run(pd.read_csv(args.hypotheses_csv))
    for model, g in t.groupby("model"):
        lost = g[g.within_part & ~g.holm_all]
        print(f"{model}: {int(g.within_part.sum())} of {len(g)} contrasts significant within their part; "
              f"{int(g.holm_all.sum())} under Holm across all, {int(g.bh_all.sum())} under Benjamini-Hochberg; "
              f"lost under Holm across all: {', '.join(lost['test']) or 'none'}")
    if args.out:
        t.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
