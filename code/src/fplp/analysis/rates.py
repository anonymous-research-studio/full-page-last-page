"""Per-cell rates with percentile-bootstrap 95% CIs, after the pre-registered exclusions (refusals
and empty replies; `--keep-empty` keeps empty replies as stops).

Usage: uv run fplp rates data/processed/pilot.csv --out results/tables/pilot_rates.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample

METRICS = ["follow_up", "missed_fetch", "extra_fetch", "followup_calls", "completion", "correct",
           "justified_correct", "disclosed", "hedged"]


def bootstrap_ci(x: np.ndarray, n_boot: int, rng: np.random.Generator) -> tuple[float, float]:
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scored_csv")
    parser.add_argument("--out", required=True)
    parser.add_argument("--by", default="model,arm,signal_form,extent,task_need", help="comma-separated grouping columns")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--keep-empty", action="store_true", help="keep empty replies as stops (sensitivity)")
    args = parser.parse_args(argv)

    raw = pd.read_csv(args.scored_csv)
    if "extra_fetch" not in raw and "unnecessary_fetch" in raw:  # scored before amendment 1 renamed it
        raw = raw.rename(columns={"unnecessary_fetch": "extra_fetch"})
    df = analysis_sample(raw, empty_as_stop=args.keep_empty)
    print(f"{len(raw) - len(df)} of {len(raw)} episodes excluded")
    keys = args.by.split(",")
    rng = np.random.default_rng(args.seed)
    rows = []
    for group, g in df.groupby(keys, dropna=False):
        group = group if isinstance(group, tuple) else (group,)
        for metric in (m for m in METRICS if m in g):
            x = g[metric].dropna().to_numpy(dtype=float)
            if len(x) == 0:
                continue
            lo, hi = bootstrap_ci(x, args.n_boot, rng)
            rows.append({**dict(zip(keys, group, strict=True)), "metric": metric, "n": len(x), "rate": x.mean(), "ci_lo": lo, "ci_hi": hi})
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
