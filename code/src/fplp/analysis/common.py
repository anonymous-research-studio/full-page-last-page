"""Shared pieces of the analysis: the item key, defaults for older scored files, the exclusion
rule, and the paired tests every pre-registered contrast uses."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.stats.contingency_tables import mcnemar

ALPHA = 0.05


def col(df: pd.DataFrame, name: str, default) -> pd.Series:
    """A column, or a constant one when older or simulated data lack it."""
    return df[name] if name in df else pd.Series(default, index=df.index)


def item_key(df: pd.DataFrame) -> pd.Series:
    """The unit of analysis: one item (task type, item index). Replicates of an item share its key."""
    return df["task_type"].astype(str) + ":" + df["item"].astype(str)


def excluded(df: pd.DataFrame, empty_as_stop: bool = False) -> pd.Series:
    """The pre-registered exclusions: refusals, and empty replies (protocol failures) unless the
    sensitivity analysis keeps them as stops."""
    out = col(df, "stop_reason", "").astype(str) == "refusal"
    if not empty_as_stop:
        out |= col(df, "empty_reply", 0).fillna(0).astype(int) == 1
    return out


def analysis_sample(df: pd.DataFrame, empty_as_stop: bool = False) -> pd.DataFrame:
    """Episodes left after the exclusions, with the item key and defaults for missing columns. Retest
    episodes (second runs of a random 10% of conditions) are left out: they measure reproducibility
    (`retest_reliability`), and no hypothesis test uses them."""
    d = df[~excluded(df, empty_as_stop) & (col(df, "arm", "core") != "retest")].copy()
    d["key"] = item_key(d)
    for name, default in [("answer_format", "final_line"), ("conflict", None), ("stated_completeness", None),
                          ("disclosure_flag", 0), ("replicate", 0), ("settled_on_page1", 0), ("own_small_page", 0),
                          ("disclosure_stratum", None), ("followup_calls", 0), ("documented", True)]:
        d[name] = col(d, name, default)
    if "follow_up" in d:
        d["responsive_follow_up"] = col(d, "responsive_follow_up", None)
        d["responsive_follow_up"] = d["responsive_follow_up"].fillna(d["follow_up"])  # older scored files
    d["evidence_seen"] = col(d, "evidence_seen", None)
    d["evidence_seen"] = d["evidence_seen"].fillna(col(d, "completion", 0))  # scored before the column existed
    d["justified_correct"] = col(d, "justified_correct", 0)
    return d


def exclusion_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per model: first-run episodes, each exclusion, and episodes kept; truncation and the tool-call
    cap are reported but not excluded. Retests (second runs, used only for reliability) are counted apart."""
    retest = col(df, "arm", "core") == "retest"
    retests = retest.groupby(df["model"]).sum().rename("retests")
    df = df[~retest]
    g = pd.DataFrame({
        "model": df["model"],
        "episodes": 1,
        "empty_reply": col(df, "empty_reply", 0).fillna(0).astype(int),
        "refusal": (col(df, "stop_reason", "").astype(str) == "refusal").astype(int),
        "truncated": col(df, "truncated", 0).fillna(0).astype(int),
        "hit_cap": col(df, "hit_cap", 0).fillna(0).astype(int),
        "kept": (~excluded(df)).astype(int),
    }).groupby("model").sum()
    return g.join(retests).fillna({"retests": 0}).astype({"retests": int}).reset_index()


def agresti_min(b: int, c: int, n: int, level: float) -> tuple[float, float]:
    """Adjusted Wald interval for a paired difference of proportions (Agresti and Min, 2005): add
    one half to each cell of the 2x2 table. b and c are the discordant counts (x=1,y=0 and x=0,y=1)."""
    z = norm.ppf(1 - (1 - level) / 2)
    nn = n + 2
    p12, p21 = (b + 0.5) / nn, (c + 0.5) / nn
    diff = p12 - p21
    se = np.sqrt((p12 + p21 - diff**2) / nn)
    return float(max(-1.0, diff - z * se)), float(min(1.0, diff + z * se))


def sign_flip_p(d: np.ndarray, rng: np.random.Generator, n_perm: int) -> float:
    """Two-sided permutation p-value for a mean paired difference of zero: under the null, each
    item's difference is equally likely to have either sign."""
    observed = abs(d.mean())
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_perm, len(d)))
    flipped = np.abs((signs * d).mean(axis=1))
    return float((1 + (flipped >= observed - 1e-12).sum()) / (n_perm + 1))


def paired(a: pd.DataFrame, b: pd.DataFrame, value: str, rng: np.random.Generator, level: float = 0.95,
           n_boot: int = 2000, n_perm: int = 10000) -> dict:
    """Mean of a minus mean of b over items present on both sides, each side averaged per item.

    The test follows the design, not the values: when each item has exactly one binary outcome on
    each side (one run per item, one form per side), McNemar's exact test and the Agresti-Min
    interval; when a side averages several episodes per item (replicates, or forms pooled), a
    sign-flip permutation test and a percentile bootstrap over items."""
    single = bool(len(a)) and bool(len(b)) and a.groupby("key").size().max() == 1 and b.groupby("key").size().max() == 1
    x = a.groupby("key")[value].mean()
    y = b.groupby("key")[value].mean()
    common = x.index.intersection(y.index)
    n = len(common)
    if n == 0:
        return {"n": 0, "diff": np.nan, "lo": np.nan, "hi": np.nan, "p": np.nan, "method": "no paired items"}
    xs, ys = x[common].to_numpy(dtype=float), y[common].to_numpy(dtype=float)
    d = xs - ys
    if single and np.isin(xs, (0.0, 1.0)).all() and np.isin(ys, (0.0, 1.0)).all():
        b10, b01 = int(((xs == 1) & (ys == 0)).sum()), int(((xs == 0) & (ys == 1)).sum())
        table = [[int(((xs == 1) & (ys == 1)).sum()), b10], [b01, int(((xs == 0) & (ys == 0)).sum())]]
        p = float(mcnemar(table, exact=True).pvalue)
        lo, hi = agresti_min(b10, b01, n, level)
        method = "McNemar exact; Agresti-Min CI"
    else:
        p = sign_flip_p(d, rng, n_perm)
        boot = rng.choice(d, size=(n_boot, n), replace=True).mean(axis=1)
        tail = (1 - level) / 2
        lo, hi = float(np.quantile(boot, tail)), float(np.quantile(boot, 1 - tail))
        method = "sign-flip permutation; bootstrap CI"
    return {"n": n, "diff": float(d.mean()), "lo": lo, "hi": hi, "p": p, "method": method}


def holm(pvalues: list[float], alpha: float = ALPHA) -> list[bool]:
    """Holm's step-down procedure; a missing p-value is never rejected."""
    order = sorted(range(len(pvalues)), key=lambda i: np.nan_to_num(pvalues[i], nan=1.0))
    reject = [False] * len(pvalues)
    for rank, i in enumerate(order):
        if not pvalues[i] <= alpha / (len(pvalues) - rank):
            break
        reject[i] = True
    return reject


RETEST_OUTCOMES = ["follow_up", "evidence_seen", "correct", "disclosure_flag"]
MODEL_NAMES = {"gpt-oss-120b": "gpt-oss-120b", "mistral-medium-3-5": "Mistral Medium 3.5",
               "claude-sonnet-5-5": "Claude Sonnet 5.5", "nemotron-3-super": "Nemotron 3 Super"}


def retest_reliability(df: pd.DataFrame) -> pd.DataFrame:
    """Per model and outcome, how often a condition's retest matched its first run: the share of
    identical outcomes and Cohen's kappa, over retest pairs where neither run was excluded."""
    d = df[~excluded(df)]
    keys = [c for c in ["model", "signal_form", "conflict", "extent", "task_type", "item", "phrasing",
                        "limit_stated", "documented", "placement", "answer_format"] if c in d]
    retests = d[col(d, "arm", "core") == "retest"]
    if retests.empty:
        return pd.DataFrame()
    firsts = d[(col(d, "arm", "core") != "retest") & (col(d, "replicate", 0) == 0)]
    left, right = firsts.copy(), retests.copy()
    left[keys], right[keys] = left[keys].fillna("").astype(str), right[keys].fillna("").astype(str)
    pairs = left.merge(right, on=keys, suffixes=("_first", "_retest"))
    rows = []
    for model, g in pairs.groupby("model"):
        for outcome in [o for o in RETEST_OUTCOMES if f"{o}_first" in g]:
            a, b = g[f"{outcome}_first"].astype(int), g[f"{outcome}_retest"].astype(int)
            po = float((a == b).mean())
            pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
            rows.append({"model": model, "outcome": outcome, "pairs": len(g), "agreement": po,
                         "kappa": (po - pe) / (1 - pe) if pe < 1 else np.nan,
                         "rate_first": float(a.mean()), "rate_retest": float(b.mean())})
    return pd.DataFrame(rows)
