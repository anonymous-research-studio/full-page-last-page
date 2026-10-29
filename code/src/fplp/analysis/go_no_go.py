"""The pilot decision rule in prereg/PREREGISTRATION.md, section 6.

GO when both hold:
  1. protocol health: under 5% of each model's episodes end with an empty reply (a planned model with
     no scored episodes fails);
  2. for at least one model, at least one contrast has a Holm-corrected p below .05 (Holm across
     that model's contrasts) and a difference of at least 15 points:
       RQ1: an explicit form minus no signal, fetch when more rows exist and are needed, counted
            only if the no-signal rate lies between 10% and 90%;
       RQ2: no signal minus a truthful terminal form, fetch past a full last page.
Otherwise NO GO. Contrasts are paired by item (fplp.analysis.common.paired). With the pilot config
(the default), the planned models and episodes are known: a planned model without data fails
protocol health, and a verdict on an incomplete run is marked provisional.

Usage: uv run fplp go-no-go data/processed/pilot.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, col, holm, paired

THRESHOLD = 0.15
HEALTH = 0.05  # largest acceptable share of empty replies per model


def preregistered_decision(df: pd.DataFrame, threshold: float = THRESHOLD, n_boot: int = 2000, seed: int = 0,
                           planned: dict[str, set[str]] | None = None) -> dict:
    """The decision; `planned` (episode ids per model, from the run config) adds the coverage check."""
    rng = np.random.default_rng(seed)
    health = col(df, "empty_reply", 0).fillna(0).groupby(df["model"]).mean()
    healthy = bool((health < HEALTH).all())
    coverage = {}
    if planned is not None:
        scored = df.groupby("model")["episode_id"].apply(set) if len(df) else pd.Series(dtype=object)
        coverage = {m: (len(ids & scored.get(m, set())), len(ids)) for m, ids in planned.items()}
        healthy = healthy and all(done > 0 for done, _ in coverage.values())  # no data is not health
    d = analysis_sample(df)
    d = d[d["settled_on_page1"] == 0]  # exists "yes" answered on page 1: no fetch needed whatever the signal
    core = d[(d["arm"] == "core") & (d["answer_format"] == "final_line")]
    passing, detail, table = [], [], []
    for model, g in core.groupby("model"):
        forms = [f for f in sorted(g["signal_form"].unique()) if f != "none"]
        need = g[(g["extent"] == "more_full") & (g["task_need"] == "needs_all")]
        last = g[(g["extent"] == "last_full") & (g["task_need"] == "needs_all")]
        base = need[need.signal_form == "none"]["follow_up"].mean()
        contrasts = []
        if 0.10 <= base <= 0.90:
            contrasts += [("RQ1", f"{f} - none", f, paired(need[need.signal_form == f], need[need.signal_form == "none"],
                                                           "follow_up", rng, n_boot=n_boot)) for f in forms]
        contrasts += [("RQ2", f"none - {f}", f, paired(last[last.signal_form == "none"], last[last.signal_form == f],
                                                       "follow_up", rng, n_boot=n_boot)) for f in forms]
        sig = holm([c[3]["p"] for c in contrasts])
        ok = []
        for (rq, label, form, c), s in zip(contrasts, sig, strict=True):
            passes = bool(s and c["diff"] >= threshold)
            table.append({"model": model, "rq": rq, "contrast": label, **c, "holm_significant": s, "passes": passes})
            if passes:
                ok.append(f"{rq}:{form}")
        detail.append({"model": model, "empty_reply_rate": float(health.get(model, 0.0)),
                       "no_signal_rate_when_needed": base, "passing_contrasts": ok})
        if ok:
            passing.append(model)
    complete = all(done == total for done, total in coverage.values())
    return {"go": healthy and bool(passing), "healthy": healthy, "models_passing": passing, "detail": detail,
            "table": pd.DataFrame(table), "coverage": coverage, "complete": complete}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", help="optional CSV of every contrast (per-model health goes to <out>_models.csv)")
    parser.add_argument("--config", default="configs/runs/pilot.yaml",
                        help="run config whose planned episodes to check coverage against; `none` to skip")
    parser.add_argument("--models-file", default="configs/models.yaml")
    args = parser.parse_args(argv)

    planned = None
    if args.config != "none":
        from fplp.metrics import _plan

        planned = _plan(args.config, args.models_file)
    decision = preregistered_decision(pd.read_csv(args.scored_csv), n_boot=args.n_boot, seed=args.seed, planned=planned)
    if len(decision["table"]):
        with pd.option_context("display.width", 160, "display.max_columns", 20):
            print(decision["table"].drop(columns=["method"]).round(3).to_string(index=False))
        print()
    for row in decision["detail"]:
        room = "" if 0.10 <= row["no_signal_rate_when_needed"] <= 0.90 else " (outside 10-90%: RQ1 not counted)"
        print(f"{row['model']}: empty replies {row['empty_reply_rate']:.1%}; no-signal rate when needed "
              f"{row['no_signal_rate_when_needed']:.2f}{room}; passing: {', '.join(row['passing_contrasts']) or 'none'}")
    for model, (done, total) in decision["coverage"].items():
        print(f"{model}: {done} of {total} planned episodes scored" + ("" if done == total else "  (INCOMPLETE)"))
    if not decision["complete"]:
        print("PROVISIONAL: the run is incomplete; resume it before deciding (prereg section 5)")
    print("\nPre-registered decision:", "GO" if decision["go"] else "NO GO",
          f"(protocol health ok: {decision['healthy']}; models passing: {', '.join(decision['models_passing']) or 'none'})")
    if args.out:
        decision["table"].to_csv(args.out, index=False)
        out = Path(args.out)
        models = pd.DataFrame(decision["detail"]).assign(
            passing_contrasts=lambda x: x["passing_contrasts"].str.join("; "))
        models.to_csv(out.with_name(f"{out.stem}_models{out.suffix}"), index=False)


if __name__ == "__main__":
    main()
