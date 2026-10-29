"""The cost of not stopping: tool calls and input tokens added or saved by each signal (descriptive).

Not a registered or amended test; the paper reports it as a cost (interim 41 in the draft). Computed on
the amended tests' cells (`fplp.analysis.hypotheses._cells`: core arm, final-line answers, own small
pages and page-1-settled exists items left out, exclusions applied), per model:
  - means per form and cell: all tool calls (`n_calls`), follow-up calls on the target query
    (`followup_calls`), input tokens (`tokens_in`, every input token processed, cached ones included),
    and cap hits;
  - paired by item against no signal, with 95% intervals (`fplp.analysis.common.paired`): calls and
    tokens a signal adds where more rows exist (form - none, on full and on short first pages), and what an
    end signal saves on a real full last page (none - form); each form, and the main forms pooled
    ("any signal": each item's mean over the forms).

  uv run python scripts/cost_of_not_stopping.py data/processed/main.csv --out results/tables/main_cost.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, paired
from fplp.analysis.hypotheses import MAIN_EXPLICIT, _cells

MEASURES = ["n_calls", "followup_calls", "tokens_in"]
LABEL = "descriptive (cost; not a registered or amended test)"


def cost(scored: pd.DataFrame, seed: int = 0, n_boot: int = 2000) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    means, contrasts = [], []
    for model, d in analysis_sample(scored).groupby("model"):
        c = _cells(d, own_small_page=True)
        cells = {"more rows exist, full page 1": c["need"], "more rows exist, short page 1": c["more_short"],
                 "real full last page": c["last"]}
        for cell_name, cell in cells.items():
            for form, g in cell.groupby("signal_form"):
                means.append({"model": model, "cell": cell_name, "form": form, "episodes": len(g),
                              **{m: g[m].mean() for m in MEASURES}, "cap_hits": int(g["hit_cap"].sum())})
            saving = cell_name == "real full last page"  # an end signal saves what no signal costs
            pooled = cell[cell.signal_form.isin(MAIN_EXPLICIT)]
            for form, side in [*((f, cell[cell.signal_form == f]) for f in MAIN_EXPLICIT), ("any signal", pooled)]:
                none = cell[cell.signal_form == "none"]
                for m in MEASURES:
                    a, b = (none, side) if saving else (side, none)
                    t = paired(a, b, m, rng, n_boot=n_boot)
                    contrasts.append({"model": model, "cell": cell_name, "measure": m,
                                      "contrast": f"none - {form}" if saving else f"{form} - none",
                                      "reads_as": "saved by the end signal" if saving else "added by the signal",
                                      **t, "label": LABEL})
    return pd.DataFrame(means), pd.DataFrame(contrasts)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scored_csv")
    p.add_argument("--out", help="CSV of the paired contrasts; the per-form means go beside it (_means.csv)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-boot", type=int, default=2000)
    args = p.parse_args(argv)
    means, contrasts = cost(pd.read_csv(args.scored_csv), args.seed, args.n_boot)
    with pd.option_context("display.width", 220, "display.max_rows", 400):
        print(contrasts[contrasts["measure"] != "followup_calls"][["model", "cell", "measure", "contrast", "n", "diff", "lo", "hi"]]
              .round(3).to_string(index=False))
    if args.out:
        contrasts.to_csv(args.out, index=False)
        means.to_csv(args.out.replace(".csv", "_means.csv"), index=False)


if __name__ == "__main__":
    main()
