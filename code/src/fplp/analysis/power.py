"""Power of pre-registered tests by items per cell, from simulated data with assumed true rates.

  --test go   the pilot rule (`fplp go-no-go`): share of simulated pilots that GO; with every form at
              the baseline rate, the same share is the false-GO rate.
  --test h1a  H1a in one model: every explicit form beats no signal when the fetch is needed
              (McNemar, Holm across forms), as in `fplp hypotheses`.
  --test amended  the amended family's A1, H1 and H2 verdicts per model (supported, not supported,
              not estimable), with per-model rates from --rates-file (YAML: model -> rate string).

Simulated designs: forms x (needs-all with more rows, page-1-sufficient, full last page), one
replicate, item difficulty shared across forms. Assumed rates are inputs, not findings; vary them to
see how sensitive the plan is.

Usage:
  uv run fplp power --rates "none=0.2,has_more=0.35,next_cursor=0.35,nl_note_json=0.35"
  uv run fplp power --test h1a --models 1 --items 100 \
      --forms none,has_more,next_cursor,total_count,nl_note_json,cursor_plus_note
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, holm, paired
from fplp.analysis.go_no_go import preregistered_decision
from fplp.analysis.hypotheses import run as run_hypotheses
from fplp.analysis.simulate import parse_rates, simulate


def h1a_supported(df: pd.DataFrame, seed: int) -> list[bool]:
    """Per model: every explicit form minus no signal, fetch when needed, Holm-significant and positive."""
    rng = np.random.default_rng(seed)
    d = analysis_sample(df)
    out = []
    for _, g in d.groupby("model"):
        need = g[(g["extent"] == "more_full") & (g["task_need"] == "needs_all")]
        forms = [f for f in sorted(need["signal_form"].unique()) if f != "none"]
        tests = [paired(need[need.signal_form == f], need[need.signal_form == "none"], "follow_up", rng) for f in forms]
        sig = holm([t["p"] for t in tests])
        out.append(all(s and t["diff"] > 0 for t, s in zip(tests, sig, strict=True)))
    return out


def amended_power(args, forms: list[str]) -> None:
    """Share of simulations giving each amended verdict (A1, H1, H2) per model."""
    from pathlib import Path

    import yaml

    spec = yaml.safe_load(Path(args.rates_file).read_text()) if args.rates_file else {"m0": args.rates}
    by_model = {m: parse_rates(r) for m, r in spec.items()}
    tally: dict = {}
    for n in map(int, args.items.split(",")):
        for s in range(args.sims):
            df = simulate(forms, list(by_model), n, item_sd=args.item_sd, model_sd=0.0, seed=s, rates_by_model=by_model)
            detail, _ = run_hypotheses(df, n_boot=args.n_boot, seed=s, families=("amended",))
            for r in detail[(detail.part == "overall") & detail.hypothesis.isin(["A1", "H1", "H2"])].itertuples():
                verdict = "not estimable" if not r.estimable else ("supported" if r.supported is True else "not supported")
                key = (n, r.model, r.hypothesis)
                tally.setdefault(key, {"supported": 0, "not supported": 0, "not estimable": 0})[verdict] += 1
    rows = [{"items_per_cell": n, "model": m, "hypothesis": h, **{k: v / args.sims for k, v in c.items()}}
            for (n, m, h), c in sorted(tally.items())]
    print(pd.DataFrame(rows).to_string(index=False))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test", choices=["go", "h1a", "amended"], default="go")
    parser.add_argument("--rates-file", help="YAML mapping model -> rates string (as --rates), for --test amended")
    parser.add_argument("--forms", default="none,has_more,next_cursor,nl_note_json")
    parser.add_argument("--models", type=int, default=2)
    parser.add_argument("--rates", default="none=0.2,has_more=0.35,next_cursor=0.35,nl_note_json=0.35")
    parser.add_argument("--items", default="30,50,100")
    parser.add_argument("--item-sd", type=float, default=1.0)
    parser.add_argument("--sims", type=int, default=200)
    parser.add_argument("--n-boot", type=int, default=200)
    args = parser.parse_args(argv)

    rates = parse_rates(args.rates)
    forms = args.forms.split(",")
    models = [f"m{i}" for i in range(args.models)]
    if args.test == "amended":
        amended_power(args, forms)
        return
    rows = []
    for n in map(int, args.items.split(",")):
        hits = []
        for s in range(args.sims):
            df = simulate(forms, models, n, rates, item_sd=args.item_sd, seed=s)
            hits += [preregistered_decision(df, n_boot=args.n_boot, seed=s)["go"]] if args.test == "go" \
                else h1a_supported(df, s)
        rows.append({"items_per_cell": n, f"power_{args.test}": float(np.mean(hits))})
        print(rows[-1])
    print()
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
