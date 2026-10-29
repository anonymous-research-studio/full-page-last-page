"""Stratum-weighted parser error rate per model, from filled-in audit worksheets (descriptive).

An error is a reply where the auditor disagrees with the scorer's correctness reading (verdict
"disagree"). Each reply carries its stratum's weight (population / sampled, from the sampler's manifest,
in the worksheet's `weight` column), so the weighted rate estimates the share of the model's main-study
replies whose correctness the parser misreads. Per model:
  - the weighted error rate over the replies with "agree" or "disagree", with two 95% intervals: a
    percentile bootstrap that resamples replies within each stratum (`bootstrap_lo`, `bootstrap_hi`),
    which collapses to a point when every stratum's verdicts agree with each other; and a Wilson interval
    on the Kish effective sample size (`wilson_kish_lo`, `wilson_kish_hi`, `kish_n_eff`), computed by the
    registered H5a fallback's own function, which keeps a usable upper bound when no reply is an error
    (added 2026-10-25, before any verdicts were filled in);
  - bounds for the unsure verdicts: every unsure counted as agree (lower) and as disagree (upper);
  - the unweighted rate, the counts per verdict, and the share of the population (by weight) that the
    agree/disagree replies cover; blank verdicts are reported as not yet audited;
  - per stratum: weight, replies, disagree, unsure, blank.
The verdicts come from a verdicts-only file (`audit_id`, `verdict`, `note`, pre-filled with the part's
ids), merged with its worksheet by `audit_id`; each part is given as a pair, because audit ids restart at 1
in every part. The script stops, naming the file and the ids, if a verdicts file has an id missing from
its worksheet, an id the worksheet lacks, or a duplicated id; and if an episode appears in two parts.
Verdicts are read case-insensitively; anything other than agree, disagree, unsure or blank stops the
script and names the audit ids. The worksheet's own `verdict` and `note` columns are ignored.

  uv run python scripts/audit_error_rate.py \
      --part REVIEW/final/audit_worksheet_part1.csv REVIEW/final/audit_verdicts_part1.csv \
      [--part REVIEW/final/audit_worksheet_part2.csv REVIEW/final/audit_verdicts_part2.csv] \
      --out REVIEW/final/audit_error_rates.csv
or, for the combined blinded worksheet (`scripts/audit_combined.py`), whose key carries model, stratum and weight:
  uv run python scripts/audit_error_rate.py \
      --part REVIEW/final/audit_key_combined.csv REVIEW/final/audit_verdicts_combined.csv --out ...
Give either the part files or the combined files, not both (an episode would appear twice, which stops the script).
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from fplp.analysis.hypotheses import _weighted_item_wilson

VERDICTS = {"agree", "disagree", "unsure", ""}


def _ids(values: pd.Series) -> str:
    return ", ".join(str(i) for i in sorted(values))


def merge_part(worksheet: str, verdicts: str) -> pd.DataFrame:
    """One part's worksheet with its verdicts file, matched one to one by audit_id."""
    w = pd.read_csv(worksheet).drop(columns=["verdict", "note"], errors="ignore")
    v = pd.read_csv(verdicts, dtype={"verdict": str, "note": str})
    if missing_cols := {"audit_id", "verdict"} - set(v.columns):
        raise SystemExit(f"{verdicts}: missing column(s) {', '.join(sorted(missing_cols))}")
    for name, frame in ((worksheet, w), (verdicts, v)):
        dup = frame.loc[frame["audit_id"].duplicated(), "audit_id"]
        if len(dup):
            raise SystemExit(f"{name}: duplicated audit id(s) {_ids(dup.unique())}")
    if missing := set(w["audit_id"]) - set(v["audit_id"]):
        raise SystemExit(f"{verdicts}: audit id(s) missing, present in {worksheet}: {_ids(missing)}")
    if extra := set(v["audit_id"]) - set(w["audit_id"]):
        raise SystemExit(f"{verdicts}: audit id(s) not in {worksheet}: {_ids(extra)}")
    d = w.merge(v[["audit_id", "verdict", *(["note"] if "note" in v else [])]], on="audit_id", validate="one_to_one")
    d["verdict"] = d["verdict"].fillna("").str.strip().str.lower()
    bad = d.loc[~d["verdict"].isin(VERDICTS), "audit_id"]
    if len(bad):
        raise SystemExit(f"{verdicts}: verdict must be agree, disagree, unsure or blank; check audit id(s) {_ids(bad)}")
    return d


def read(parts: list[tuple[str, str]]) -> pd.DataFrame:
    d = pd.concat([merge_part(w, v) for w, v in parts], ignore_index=True)
    if d.duplicated(["model", "episode_id"]).any():
        raise SystemExit("an episode appears in two parts")
    return d


def _weighted(d: pd.DataFrame, error: pd.Series) -> float:
    return float((d["weight"] * error).sum() / d["weight"].sum()) if len(d) else float("nan")


def _bootstrap(d: pd.DataFrame, rng: np.random.Generator, n_boot: int) -> tuple[float, float]:
    """Resample replies within each stratum; each stratum keeps its weight (population / sampled)."""
    groups = [(g["weight"].iloc[0] * len(g), (g["verdict"] == "disagree").to_numpy(float)) for _, g in d.groupby("stratum")]
    total = sum(w for w, _ in groups)
    if not total:
        return float("nan"), float("nan")
    stats = np.zeros(n_boot)
    for w, e in groups:
        stats += w / total * rng.choice(e, size=(n_boot, len(e)), replace=True).mean(axis=1)
    return float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))


def rates(d: pd.DataFrame, seed: int = 0, n_boot: int = 2000) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    per_model, per_stratum = [], []
    for model, g in d.groupby("model"):
        judged = g[g["verdict"].isin(["agree", "disagree"])]
        decided = g[g["verdict"].isin(["agree", "disagree", "unsure"])]
        lo, hi = _bootstrap(judged, rng, n_boot)
        errors = (judged["verdict"] == "disagree").astype(float)
        wilson = _weighted_item_wilson(errors, judged["episode_id"], judged["weight"]) if len(judged) else {}
        n_eff = float(judged["weight"].sum() ** 2 / (judged["weight"] ** 2).sum()) if len(judged) else float("nan")
        per_model.append({
            "model": model, "replies": len(g), "agree": int((g["verdict"] == "agree").sum()),
            "disagree": int((g["verdict"] == "disagree").sum()), "unsure": int((g["verdict"] == "unsure").sum()),
            "not_yet_audited": int((g["verdict"] == "").sum()),
            "weighted_error_rate": _weighted(judged, judged["verdict"] == "disagree"),
            "bootstrap_lo": lo, "bootstrap_hi": hi, "wilson_kish_lo": wilson.get("lo", float("nan")),
            "wilson_kish_hi": wilson.get("hi", float("nan")), "kish_n_eff": n_eff,
            "lower_bound_unsure_as_agree": _weighted(decided, decided["verdict"] == "disagree"),
            "upper_bound_unsure_as_disagree": _weighted(decided, decided["verdict"].isin(["disagree", "unsure"])),
            "unweighted_error_rate": float((judged["verdict"] == "disagree").mean()) if len(judged) else float("nan"),
            "population_share_covered": float(judged["weight"].sum() / g["weight"].sum()) if len(g) else float("nan"),
        })
        for stratum, s in g.groupby("stratum"):
            per_stratum.append({"model": model, "stratum": stratum, "weight": s["weight"].iloc[0], "replies": len(s),
                                "disagree": int((s["verdict"] == "disagree").sum()),
                                "unsure": int((s["verdict"] == "unsure").sum()), "blank": int((s["verdict"] == "").sum())})
    return pd.DataFrame(per_model), pd.DataFrame(per_stratum)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--part", nargs=2, action="append", required=True, metavar=("WORKSHEET", "VERDICTS"),
                   help="a part's worksheet CSV and its verdicts CSV; repeat for each part")
    p.add_argument("--out", help="CSV of the per-model rates; the per-stratum counts go beside it (_strata.csv)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-boot", type=int, default=2000)
    args = p.parse_args(argv)
    per_model, per_stratum = rates(read([tuple(part) for part in args.part]), args.seed, args.n_boot)
    with pd.option_context("display.width", 220, "display.max_columns", 30):
        print(per_model.round(4).to_string(index=False))
        print()
        print(per_stratum.to_string(index=False))
    if args.out:
        per_model.to_csv(args.out, index=False)
        per_stratum.to_csv(args.out.replace(".csv", "_strata.csv"), index=False)


if __name__ == "__main__":
    main()
