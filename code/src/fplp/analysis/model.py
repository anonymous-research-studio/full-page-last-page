"""Logistic regression of follow-up on signal form x task need.

Two specifications:

  fixed  the pre-registered secondary analysis (prereg/PREREGISTRATION.md, section 2), descriptive
         only: model as a fixed effect, optional signal x model term, standard errors clustered by item.
  mixed  follow_up ~ signal * task_need + (1|model) + (1|item), fit by variational Bayes (statsmodels
         BinomialBayesMixedGLM). Kept for comparison, not used for inference: on simulated data it
         understated uncertainty.

Refusals and empty replies are excluded, as in every pre-registered analysis.

Defaults: core arm, extent more_full (page 1 full and more rows exist), so task need decides
whether a fetch is needed. Task type enters as a fixed effect, which also absorbs the tool.

Usage: uv run fplp model data/processed/pilot.csv --spec fixed --out results/tables/model_fixed.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

from fplp.analysis.common import excluded

SEPARATION = 10.0  # |log-odds| beyond this, or an undefined SE, marks a term as not estimable


def prepare(df: pd.DataFrame, exclude_forms: list[str], extent: str) -> pd.DataFrame:
    df = df[~excluded(df)]  # the pre-registered exclusions: refusals and empty replies
    d = df[(df["arm"] == "core") & ~df["signal_form"].isin(exclude_forms)].copy()
    if "extent" in d:
        d = d[d["extent"] == extent]
    d["item_key"] = d["task_type"].astype(str) + ":" + d["item"].astype(str)
    return d


def _page1_interactions(d: pd.DataFrame, baseline: str) -> dict[str, str]:
    """Add one 0/1 column per non-baseline form: that form on a page-1-sufficient task.

    Task need is a function of task type, so its main effect is absorbed by C(task_type), and a
    formula interaction would be coded at full rank and collide with it. Explicit columns against
    the baseline form keep the design identifiable: each estimates how that form's effect differs
    between page-1-sufficient and needs-all tasks.
    """
    page1 = (d["task_need"] == "page1_sufficient").astype(int)
    names = {}
    for i, form in enumerate(sorted(f for f in d["signal_form"].unique() if f != baseline)):
        col = f"x_page1_{i}"
        d[col] = (d["signal_form"] == form).astype(int) * page1
        names[col] = f"{form} x page1_sufficient"
    return names


def fit_fixed(d: pd.DataFrame, baseline: str, by_model: bool):
    d = d.copy()
    signal = f"C(signal_form, Treatment('{baseline}'))"
    interactions = _page1_interactions(d, baseline)
    rhs = " + ".join([signal, *interactions, "C(task_type)", "C(model)"])
    if by_model:
        rhs += f" + {signal}:C(model)"
    groups = pd.factorize(d["item_key"])[0]
    result = smf.glm(f"follow_up ~ {rhs}", data=d, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )
    table = pd.DataFrame({
        "term": [interactions.get(t, t) for t in result.params.index],
        "estimate": result.params.values,
        "se": result.bse.values,
        "ci_lo": result.conf_int()[0].values,
        "ci_hi": result.conf_int()[1].values,
        "p": result.pvalues.values,
    })
    # A cell at 0% or 100% (say, a model that always fetches without a signal) separates the data:
    # its terms run off to large log-odds with undefined standard errors. They are reported as not
    # estimable rather than interpreted (prereg section 2).
    table["estimable"] = np.isfinite(table["se"]) & (table["estimate"].abs() < SEPARATION)
    return result, table


def fit_mixed(d: pd.DataFrame, baseline: str):
    signal = f"C(signal_form, Treatment('{baseline}'))"
    model = BinomialBayesMixedGLM.from_formula(
        f"follow_up ~ {signal} * C(task_need)",
        {"model": "0 + C(model)", "item": "0 + C(item_key)"},
        d,
    )
    result = model.fit_vb()
    table = pd.DataFrame({
        "term": model.exog_names,
        "estimate": result.fe_mean,
        "se": result.fe_sd,
        "ci_lo": result.fe_mean - 1.96 * result.fe_sd,
        "ci_hi": result.fe_mean + 1.96 * result.fe_sd,
    })
    return result, table


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv")
    parser.add_argument("--spec", choices=["fixed", "mixed"], default="fixed")
    parser.add_argument("--baseline", default="none")
    parser.add_argument("--by-model", action="store_true", help="fixed spec: add signal x model interaction")
    parser.add_argument("--exclude-forms", default="", help="comma-separated forms to leave out")
    parser.add_argument("--extent", default="more_full")
    parser.add_argument("--out", help="optional CSV of coefficients (log-odds)")
    args = parser.parse_args(argv)

    d = prepare(pd.read_csv(args.scored_csv), [f for f in args.exclude_forms.split(",") if f], args.extent)
    if args.spec == "fixed":
        result, table = fit_fixed(d, args.baseline, args.by_model)
    else:
        result, table = fit_mixed(d, args.baseline)
    print(result.summary())
    if "estimable" in table and not table["estimable"].all():
        print(f"\nNOT ESTIMABLE (separation): {', '.join(table.loc[~table['estimable'], 'term'])}")
    if args.out:
        table.to_csv(args.out, index=False)
        print(f"\ncoefficients -> {args.out}")


if __name__ == "__main__":
    main()
