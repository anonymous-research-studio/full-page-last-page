"""Tests of H1 to H5 per model, from scored episodes (`fplp score --config`), in three families.

  registered   the tests as registered on 19 Oct 2026 (prereg/PREREGISTRATION.md, section 2),
               computed unchanged and always reported;
  amended      the tests added by prereg/AMENDMENT-1.md (20 Oct 2026, before any pilot episode)
               after a design review found that some registered tests pass or fail by construction:
               a signal-value test a ceiling cannot defeat, H1a/H2a marked not estimable at a
               ceiling or floor, H2b on its own, an information-matched natural-language contrast
               with an equivalence test, controls that make H3 interpretable, H4's consequence for
               answers, H5a where disclosure is warranted, and H5b in warranted cells with an
               intention-to-treat outcome and an informativeness check;
  descriptive  one-factor arms against their base cells, without verdicts.

Unit of analysis: the item (task type, item index), paired across conditions; replicates, if any,
are averaged per item first. Paired tests are two-sided (fplp.analysis.common.paired): McNemar's
exact test with the Agresti-Min interval when each item has one binary outcome per side, otherwise
a sign-flip permutation test with a bootstrap interval over items. Holm correction where one part
has several contrasts.

Exclusions: refusals and empty replies, counted per model. Fetch tests leave out exists "yes" items
settled by a row on page 1, and (amended family) episodes whose first call asked for fewer rows than
the page limit. Sensitivity analyses: both families with empty replies kept as stops (as registered);
the amended family without the oldest-date task, without the export task, and counting only
responsive follow-ups.

Across models: registered verdicts need support in a majority of the confirmatory models (2 of 3);
amended verdicts need support in a majority of the confirmatory models where the test is estimable,
with at least two estimable.

Usage: uv run fplp hypotheses data/processed/main.csv --out results/tables/hypotheses.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from fplp.analysis.common import ALPHA, analysis_sample, exclusion_table, holm, paired, retest_reliability

STRUCTURED = ["has_more", "next_cursor", "total_count"]
NATURAL = ["nl_note_json", "cursor_plus_note"]
MAIN_EXPLICIT = STRUCTURED + NATURAL
# Registered H1b and H2b: each natural-language form against the structured form said to carry the
# same information. The second pair also adds the total and the shown range (amendment 1, issue 6).
NL_CONTRASTS = [("nl_note_json", "total_count"), ("cursor_plus_note", "next_cursor")]
FALSE_END = {"false_end": "has_more", "false_end_cursor": "next_cursor", "false_total": "total_count",
             "false_note": "nl_note_json"}
# H6 (amendment 1): each visible conflict against the same false end shown alone.
VISIBLE = {"visible_conflict_total": "false_end", "visible_conflict_note": "false_end_cursor"}
UNDOCUMENTED_FORMS = ["has_more", "nl_note_json"]  # the forms the documentation arm runs without the pagination cue
RARE = 0.20                  # H5a: "rarely" means the 95% upper bound of the disclosure rate is below 20%
MIN_ITEMS_H5A = 16           # amended H5a: below 16 items, even zero disclosures leave the Wilson bound above 20%
MIN_ITEMS_H5B = 10           # amended H5b: items whose outcome can vary, per part
REGISTERED_EXTENTS = ("more_full", "last_full", "more_short")  # the registered main-study extents
PRECISION_RECALL_MIN = 0.80  # below this, disclosure comes from the hand labels
BAND = (0.10, 0.90)          # amended: a no-signal rate outside this band leaves no room for H1a or H2a
EQUIVALENCE = 0.10           # amended: "no difference" between forms needs the 90% CI within 10 points
# Descriptive arms: arm -> (label, base form). Each is compared with the core cell of its base form
# on the same extent and task need.
DESCRIPTIVE_ARMS = {"phrasing": ("explicit 'all' wording", "none"), "limit": ("page limit hidden", "none"),
                    "documentation": ("pagination not documented", None),
                    "doc_wording": ("pagination documented without 'when it includes one'", None),
                    "answer_format": ("completeness field", None), "placement": ("signal before the rows", "has_more")}
PAIR_COLUMNS = ["signal_form", "conflict", "extent", "task_type", "item", "replicate", "phrasing",
                "limit_stated", "documented", "placement"]
_NO_CONFLICT = ["", "nan", "None"]  # how a missing conflict reads once pair keys are strings


def _rate_ci(x: np.ndarray, rng: np.random.Generator, n_boot: int) -> dict:
    """Mean of per-item rates with a percentile-bootstrap 95% CI over items."""
    if len(x) == 0:
        return {"n": 0, "diff": np.nan, "lo": np.nan, "hi": np.nan}
    boot = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return {"n": len(x), "diff": float(x.mean()), "lo": float(np.quantile(boot, 0.025)),
            "hi": float(np.quantile(boot, 0.975))}


def _item_wilson(values: pd.Series, keys: pd.Series) -> dict:
    """A rate whose 95% Wilson interval counts each item once (its episodes averaged). Conservative
    when an item contributes several correlated episodes, and unlike a bootstrap it gives a usable
    upper bound when no episode discloses."""
    per_item = values.astype(float).groupby(keys).mean()
    n = len(per_item)
    if n == 0:
        return {"n": 0, "diff": np.nan, "lo": np.nan, "hi": np.nan}
    lo, hi = proportion_confint(per_item.sum(), n, method="wilson")
    return {"n": n, "diff": float(per_item.mean()), "lo": float(lo), "hi": float(hi)}


def _weighted_item_wilson(values: pd.Series, keys: pd.Series, weights: pd.Series) -> dict:
    """_item_wilson with episode weights: each item counts once, scaled by the mean weight of its
    episodes (its episodes averaged with their weights), with the Kish effective number of items."""
    df = pd.DataFrame({"k": keys.to_numpy(), "w": weights.to_numpy(dtype=float),
                       "vw": values.to_numpy(dtype=float) * weights.to_numpy(dtype=float)})
    g = df.groupby("k").agg(w=("w", "sum"), vw=("vw", "sum"), n=("w", "size"))
    g = g[g["w"] > 0]
    if g.empty:
        return {"n": 0, "diff": np.nan, "lo": np.nan, "hi": np.nan}
    v = g["vw"] / g["w"]
    g["w"] = g["w"] / g["n"]  # an item with several labeled episodes counts once, not once per episode
    p = float((g["w"] * v).sum() / g["w"].sum())
    n_eff = float(g["w"].sum() ** 2 / (g["w"] ** 2).sum())
    lo, hi = proportion_confint(p * n_eff, n_eff, method="wilson")
    return {"n": len(g), "diff": p, "lo": float(lo), "hi": float(hi)}


def _cluster_gap(a: pd.DataFrame, b: pd.DataFrame, value: str, rng: np.random.Generator, n_boot: int) -> dict:
    """Mean of `value` in a minus in b (different episodes), with a bootstrap over items as clusters."""
    if not len(a) or not len(b):
        return {"n": len(a) + len(b), "diff": np.nan, "lo": np.nan, "hi": np.nan}
    keys = np.array(sorted(set(a["key"]) | set(b["key"])))
    ga, gb = a.groupby("key")[value].agg(["sum", "count"]), b.groupby("key")[value].agg(["sum", "count"])
    sa, ca = ga.reindex(keys, fill_value=0)["sum"].to_numpy(), ga.reindex(keys, fill_value=0)["count"].to_numpy()
    sb, cb = gb.reindex(keys, fill_value=0)["sum"].to_numpy(), gb.reindex(keys, fill_value=0)["count"].to_numpy()
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    with np.errstate(invalid="ignore", divide="ignore"):
        boot = sa[idx].sum(1) / ca[idx].sum(1) - sb[idx].sum(1) / cb[idx].sum(1)
    boot = boot[np.isfinite(boot)]
    diff = sa.sum() / ca.sum() - sb.sum() / cb.sum()
    return {"n": int(ca.sum() + cb.sum()), "diff": float(diff),
            "lo": float(np.quantile(boot, 0.025)) if len(boot) else np.nan,
            "hi": float(np.quantile(boot, 0.975)) if len(boot) else np.nan}


def matched_pairs(d: pd.DataFrame) -> pd.DataFrame:
    """Pairs of needs-all episodes with and without the completeness field under the same model,
    item, replicate and condition otherwise. Columns carry the suffixes _with and _without."""
    cols = [c for c in ["model", *PAIR_COLUMNS] if c in d]
    needs_all = d[d["task_need"] == "needs_all"].copy()
    # Missing values become "" first: in pandas 3, astype(str) keeps them missing, and a missing
    # conflict must read as "no false signal" in the filters below.
    needs_all[cols] = needs_all[cols].fillna("").astype(str)
    pairs = needs_all[needs_all.answer_format == "completeness"].merge(
        needs_all[needs_all.answer_format == "final_line"], on=cols, suffixes=("_with", "_without"))
    pairs["key"] = pairs["key_with"]
    return pairs


def validate_flag(labels: pd.DataFrame, scored: pd.DataFrame) -> dict:
    """The rule-based flag against the authors' consensus labels (`fplp disclosure check` output:
    episode_id, label_a, label_b, label). Returns precision, recall, whether the flag may be used,
    and the consensus label per episode id."""
    lab = labels.dropna(subset=["label"]).merge(scored[["episode_id", "disclosure_flag"]], on="episode_id")
    y, f = lab["label"].astype(int), lab["disclosure_flag"].astype(int)
    tp, fp, fn = int(((f == 1) & (y == 1)).sum()), int(((f == 1) & (y == 0)).sum()), int(((f == 0) & (y == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else np.nan
    recall = tp / (tp + fn) if tp + fn else np.nan
    # A metric is undefined only when its class is empty: no flagged replies (precision) or no
    # labeled disclosures (recall). When both are empty, flag and labels agree on every reply, so
    # the flag may be used; one empty class alone leaves the other metric at 0 and fails the rule.
    if tp + fp == 0 and tp + fn == 0:
        usable = len(lab) > 0
    else:
        usable = bool(precision >= PRECISION_RECALL_MIN and recall >= PRECISION_RECALL_MIN)
    return {"n": len(lab), "precision": precision, "recall": recall, "use_flag": usable,
            "truth": lab.set_index("episode_id")["label"].astype(int)}


def _prose(d: pd.DataFrame, validation: dict | None) -> tuple[pd.DataFrame, str]:
    """Prose disclosure: the rule-based flag, or the authors' labels where the flag failed validation
    (then only labeled episodes are used). Both judge the reply without its COMPLETENESS line."""
    if validation is not None and not validation["use_flag"]:
        d = d[d["episode_id"].isin(validation["truth"].index)].assign(
            prose_disclosed=lambda x: x["episode_id"].map(validation["truth"]).astype(float))
        return d, f"hand labels (flag precision {validation['precision']:.2f}, recall {validation['recall']:.2f})"
    d = d.assign(prose_disclosed=d["disclosure_flag"].astype(float))
    return d, "rule-based flag" + (" (validated)" if validation is not None else " (not yet validated)")


class _Rows:
    def __init__(self, family: str):
        self.family, self.rows = family, []

    def add(self, h, part, test, stats, supported, estimable=True, note=""):
        self.rows.append({"family": self.family, "hypothesis": h, "part": part, "test": test, **stats,
                          "supported": supported, "estimable": estimable, "note": note})


def _contrasts(out: _Rows, rng, n_boot, h, part, pairs, cell, label, value="follow_up"):
    """Paired contrasts (a, b) in one cell, Holm-corrected; each must be positive."""
    tests = [paired(cell[cell.signal_form == a], cell[cell.signal_form == b], value, rng, n_boot=n_boot)
             for a, b in pairs]
    sig = holm([t["p"] for t in tests])
    for (a, b), t, s in zip(pairs, tests, sig, strict=True):
        if out.family == "amended" and not t["n"]:  # no paired items: nothing to estimate
            out.add(h, part, f"{a} - {b}, {label}", t, None, estimable=False)
        else:
            out.add(h, part, f"{a} - {b}, {label}", t, bool(s and t["diff"] > 0))
    return all(s and t["diff"] > 0 for t, s in zip(tests, sig, strict=True))


def _cells(d: pd.DataFrame, own_small_page: bool) -> dict:
    fetch = d[d["settled_on_page1"] == 0]
    if own_small_page:
        fetch = fetch[fetch["own_small_page"] == 0]
    core = fetch[(fetch["arm"] == "core") & (fetch["answer_format"] == "final_line")]
    needs_all = core[core["task_need"] == "needs_all"]
    return {
        "fetch": fetch, "core": core,
        "need": needs_all[needs_all["extent"] == "more_full"],
        "last": needs_all[needs_all["extent"] == "last_full"],
        "last_short": needs_all[needs_all["extent"] == "last_short"],
        "more_short": needs_all[needs_all["extent"] == "more_short"],
        "page1": core[(core["extent"] == "more_full") & (core["task_need"] == "page1_sufficient")],
        "conflicts": fetch[(fetch["arm"] == "conflict") & (fetch["answer_format"] == "final_line")],
    }


def registered_tests(d: pd.DataFrame, n_boot: int, seed: int, validation: dict | None = None) -> list[dict]:
    """H1 to H5 exactly as registered on 19 Oct 2026."""
    rng = np.random.default_rng(seed)
    out = _Rows("registered")
    c = _cells(d, own_small_page=False)
    need, last, core, conflicts = c["need"], c["last"], c["core"], c["conflicts"]

    h1a = _contrasts(out, rng, n_boot, "H1", "a", [(f, "none") for f in MAIN_EXPLICIT], need, "fetch when needed")
    h1b = _contrasts(out, rng, n_boot, "H1", "b", NL_CONTRASTS, need, "fetch when needed")
    out.add("H1", "overall", "a and b", {}, h1a and h1b)

    h2a = _contrasts(out, rng, n_boot, "H2", "a", [("none", f) for f in MAIN_EXPLICIT], last, "fetch past a full last page")
    h2b = _contrasts(out, rng, n_boot, "H2", "b", NL_CONTRASTS, c["page1"], "fetch when page 1 suffices")
    out.add("H2", "overall", "a and b", {}, h2a and h2b)

    h3 = []
    for part, extent, above in [("a", "last_full", True), ("b", "more_short", False)]:
        cell = core[(core["extent"] == extent) & (core["task_need"] == "needs_all") & core.signal_form.isin(MAIN_EXPLICIT)]
        stats = _rate_ci(cell.groupby("key")["follow_up"].mean().to_numpy(), rng, n_boot)
        ok = bool(stats["lo"] > 0.5) if above else bool(stats["hi"] < 0.5)
        out.add("H3", part, f"fetch rate on {extent} with a truthful signal, {'above' if above else 'below'} 50%", stats, ok)
        h3.append(ok)
    out.add("H3", "overall", "a and b", {}, all(h3))

    none_more = need[need.signal_form == "none"]
    for cf, form in FALSE_END.items():
        fa = conflicts[conflicts["conflict"] == cf]
        out.add("H4", f"by form ({cf})", f"none - {cf}, more rows exist",
                paired(none_more, fa, "follow_up", rng, n_boot=n_boot), None)
        out.add("H4", f"by form ({cf})", f"truthful {form} - {cf}, more rows exist",
                paired(need[need.signal_form == form], fa, "follow_up", rng, n_boot=n_boot), None)
    forms = list(FALSE_END.values())
    fa = conflicts[conflicts["conflict"].isin(list(FALSE_END))]
    vs_none = paired(none_more, fa, "follow_up", rng, n_boot=n_boot)
    h4a = bool(vs_none["p"] < ALPHA and vs_none["diff"] > 0)
    out.add("H4", "a", "none - false end signals, more rows exist", vs_none, h4a)
    vs_true = paired(need[need.signal_form.isin(forms)], fa, "follow_up", rng, n_boot=n_boot)
    h4b = bool(vs_true["p"] < ALPHA and vs_true["diff"] > 0)
    out.add("H4", "b", "truthful signals - false end signals, more rows exist", vs_true, h4b)
    out.add("H4", "overall", "a and b", {"fetch_under_false": float(fa["follow_up"].mean()) if len(fa) else np.nan},
            h4a and h4b)
    out.add("H4", "manipulation check", "false end signals - true last pages (same page 1), 90% CI",
            paired(fa, last[last.signal_form.isin(forms)], "follow_up", rng, level=0.90, n_boot=n_boot), None)
    fm = conflicts[conflicts["conflict"] == "false_more"]
    out.add("H4", "exploratory", "false_more - true has_more on a last page (over-fetching)",
            paired(fm, last[last.signal_form == "has_more"], "follow_up", rng, n_boot=n_boot), None)

    # Registered context for H5b, from every episode before any hand-label filter: the rate of
    # incomplete answers in each format, in the cells where the field was crossed (false signals).
    everyone = matched_pairs(d)
    everyone = everyone[~everyone["conflict"].isin(_NO_CONFLICT)]
    out.add("H5", "context", "incompleteness: with the field - without, false-signal cells",
            paired(everyone.assign(v=(everyone["evidence_seen_with"] == 0).astype(float)),
                   everyone.assign(v=(everyone["evidence_seen_without"] == 0).astype(float)), "v", rng, n_boot=n_boot),
            None)

    # As registered, H5a pools the incomplete final-line answers of the registered main-study cells: the
    # core and false-signal cells on the registered extents. Cells added by amendment 1 are left out, so
    # the registered test computes what was registered.
    def registered_incomplete(x: pd.DataFrame) -> pd.DataFrame:
        registered_conflict = x["conflict"].isna() | x["conflict"].isin(list(FALSE_END))
        return x[x["arm"].isin(["core", "conflict"]) & registered_conflict & x["extent"].isin(REGISTERED_EXTENTS)
                 & (x["task_need"] == "needs_all") & (x["evidence_seen"] == 0) & (x["answer_format"] == "final_line")]

    population = registered_incomplete(d)
    d, source = _prose(d, validation)
    base = registered_incomplete(d)
    if validation is not None and not validation["use_flag"]:
        # The labeling sample oversamples the warranted stratum (amendment 1), so labeled answers are
        # weighted back to each stratum's share of the registered population.
        strata = lambda x: x["disclosure_stratum"].fillna("none").astype(str)  # noqa: E731
        share, labeled = strata(population).value_counts(), strata(base).value_counts()
        weights = strata(base).map(lambda k: share.get(k, 0) / labeled[k])
        stats = _weighted_item_wilson(base["prose_disclosed"], base["key"], weights)
        source += ", weighted by stratum"
    else:
        stats = _item_wilson(base["prose_disclosed"], base["key"])
    h5a = bool(stats["n"] > 0 and stats["hi"] < RARE)
    out.add("H5", "a", f"disclosure among incomplete answers, upper 95% bound < 20%; {source}", stats, h5a)
    d = d.assign(disclosed_any=(d["prose_disclosed"].astype(bool)
                                | d["stated_completeness"].isin(["partial", "unknown"])).astype(float),
                 incomplete=(d["evidence_seen"] == 0).astype(float))
    pairs = matched_pairs(d)
    pairs = pairs[~pairs["conflict"].isin(_NO_CONFLICT)]  # as registered: the field crossed with false signals only
    both = pairs[(pairs["incomplete_with"] == 1) & (pairs["incomplete_without"] == 1)]
    t = paired(both.assign(v=both["disclosed_any_with"]), both.assign(v=both["disclosed_any_without"]), "v", rng,
               n_boot=n_boot)
    h5b = bool(t["p"] < ALPHA and t["diff"] > 0)
    out.add("H5", "b", f"disclosure with the field - without, both incomplete, false-signal cells; {source}", t, h5b)
    out.add("H5", "overall", "a and b", {}, h5a and h5b)
    return out.rows


def _combine(parts: list[tuple[bool | None, bool]]) -> tuple[bool | None, bool]:
    """A hypothesis with several parts, each (supported, estimable): not supported if any estimable part
    fails; supported if every part is estimable and passes; otherwise not estimable."""
    if any(est and sup is False for sup, est in parts):
        return False, True
    if all(est for _, est in parts):
        return all(bool(sup) for sup, _ in parts), True
    return None, False


def _why_not(cell: pd.DataFrame, forms: list[str], rate: float, low: bool) -> str:
    """Why a contrast part against no signal is not estimable: missing cells first, then the band."""
    if missing := [f for f in ["none", *forms] if not (cell.signal_form == f).any()]:
        return f"no data for {', '.join(missing)}"
    return "no-signal rate below 10%" if low else "no-signal rate above 90%"


def _rate(cell: pd.DataFrame, value: str) -> float:
    return float(cell[value].mean()) if len(cell) else np.nan


def amended_tests(d: pd.DataFrame, n_boot: int, seed: int, validation: dict | None = None,
                  value: str = "follow_up") -> list[dict]:
    """The tests added by amendment 1. `value` is the fetch outcome (responsive_follow_up in one
    sensitivity analysis). A part is "not estimable" when its cells are empty, when a ceiling or floor
    leaves no room for the predicted direction, or when it has fewer items than its pre-specified minimum."""
    rng = np.random.default_rng(seed)
    out = _Rows("amended")
    c = _cells(d, own_small_page=True)
    need, last, conflicts = c["need"], c["last"], c["conflicts"]

    # A1 (RQ1-RQ2): the signal's value drives fetching. A no-signal page looks the same whether or not
    # more rows exist, so the comparison of the same form on the two extents cannot be defeated by a
    # ceiling or floor in the no-signal rate; with no signal it is zero in expectation (a reference): nothing on
    # a no-signal page tells the extents apart, though page-1 rows differ for some tasks and sampling adds noise.
    a1, a1_est = _contrasts_across(out, rng, n_boot, need, last, value)
    a1_missing = [f for f in MAIN_EXPLICIT if not ((need.signal_form == f).any() and (last.signal_form == f).any())]
    out.add("A1", "overall", "every main explicit form: fetch when more rows exist - fetch on a real last page",
            {}, a1 if a1_est else None, estimable=a1_est,
            note="" if a1_est else f"not estimable: no data for {', '.join(a1_missing) or 'some paired items'}")

    # H1: (a) as registered, not estimable when the no-signal rate exceeds 90%; (b) the information-matched
    # pair, not estimable when total_count's rate exceeds 90% (no room for the note to be higher).
    p_need = _rate(need[need.signal_form == "none"], value)
    est1a = bool(p_need <= BAND[1]) and all((need.signal_form == f).any() for f in MAIN_EXPLICIT)
    h1a = _contrasts(out, rng, n_boot, "H1", "a", [(f, "none") for f in MAIN_EXPLICIT], need, "fetch when needed", value)
    nl_cell, tc_cell = need[need.signal_form == "nl_note_json"], need[need.signal_form == "total_count"]
    nl = paired(nl_cell, tc_cell, value, rng, level=0.90, n_boot=n_boot)
    nl_p = paired(nl_cell, tc_cell, value, rng, n_boot=n_boot)["p"]
    est1b = bool(nl["n"] and _rate(tc_cell, value) <= BAND[1])
    equivalent = bool(nl["n"] and nl["lo"] > -EQUIVALENCE and nl["hi"] < EQUIVALENCE)
    h1b = bool(nl_p < ALPHA and nl["diff"] > 0)
    out.add("H1", "b (information-matched)", "nl_note_json - total_count, fetch when needed (90% CI)", {**nl, "p": nl_p},
            h1b if est1b else None, estimable=est1b, note="equivalent within 10 points" if equivalent else "")
    out.add("H1", "descriptive", "cursor_plus_note - next_cursor: adding a range-and-total note, fetch when needed",
            paired(need[need.signal_form == "cursor_plus_note"], need[need.signal_form == "next_cursor"], value, rng,
                   n_boot=n_boot), None)
    sup, est = _combine([(h1a if est1a else None, est1a), (h1b if est1b else None, est1b)])
    out.add("H1", "overall", f"a and b; no-signal rate when needed {p_need:.2f}", {}, sup, estimable=est,
            note="" if est1a else f"a not estimable: {_why_not(need, MAIN_EXPLICIT, p_need, low=False)}")

    # H2: (a) as registered, not estimable when the no-signal rate on a real last page is below 10%.
    p_last = _rate(last[last.signal_form == "none"], value)
    est2 = bool(p_last >= BAND[0]) and all((last.signal_form == f).any() for f in MAIN_EXPLICIT)
    h2a = _contrasts(out, rng, n_boot, "H2", "a", [("none", f) for f in MAIN_EXPLICIT], last,
                     "fetch past a full last page", value)
    out.add("H2", "overall", f"a only (b is now H2b); no-signal rate on a real last page {p_last:.2f}", {},
            h2a if est2 else None, estimable=est2,
            note="" if est2 else f"not estimable: {_why_not(last, MAIN_EXPLICIT, p_last, low=True)}")
    # H2b on its own: the information-matched pair only (a floor is a valid null here: the prediction is
    # that the note raises fetching above total_count's rate).
    page1 = c["page1"]
    h2b_t = paired(page1[page1.signal_form == "nl_note_json"], page1[page1.signal_form == "total_count"], value, rng,
                   n_boot=n_boot)
    h2b, est2b = bool(h2b_t["p"] < ALPHA and h2b_t["diff"] > 0), bool(h2b_t["n"])
    out.add("H2b", "a", "nl_note_json - total_count, fetch when page 1 suffices", h2b_t, h2b if est2b else None,
            estimable=est2b)
    out.add("H2b", "overall", "information-matched pair only", {}, h2b if est2b else None, estimable=est2b)

    # H3 is interpretable only for a model that uses the row count without a signal (it fetches after a
    # full page and not after a short one). H3a then also needs the fetch past a full last page to exceed
    # the fetch past a short last page (both with a truthful terminal signal): otherwise a habit of
    # checking every terminal signal, not the row count, would explain it.
    none_full = need[need.signal_form == "none"]
    none_short = c["more_short"][c["more_short"].signal_form == "none"]
    count_use = paired(none_full, none_short, value, rng, n_boot=n_boot)
    uses_count = bool(count_use["n"] and count_use["p"] < ALPHA and count_use["diff"] > 0)
    out.add("H3", "context: row-count use", "no signal: fetch after a full page - after a short page", count_use, None)
    signal_last = last[last.signal_form.isin(MAIN_EXPLICIT)]
    signal_last_short = c["last_short"][c["last_short"].signal_form.isin(MAIN_EXPLICIT)]
    signal_more_short = c["more_short"][c["more_short"].signal_form.isin(MAIN_EXPLICIT)]
    checking = paired(signal_last, signal_last_short, value, rng, n_boot=n_boot)
    full_specific = bool(checking["n"] and checking["p"] < ALPHA and checking["diff"] > 0)
    est3a = uses_count and bool(checking["n"]) and bool(len(signal_last))
    est3b = uses_count and bool(len(signal_more_short))
    out.add("H3", "control: full vs short last page", "truthful signal: fetch past a full last page - past a short one",
            checking, full_specific if est3a else None, estimable=est3a)
    rate_last = _rate_ci(signal_last.groupby("key")[value].mean().to_numpy(), rng, n_boot)
    rate_short = _rate_ci(signal_more_short.groupby("key")[value].mean().to_numpy(), rng, n_boot)
    h3a = bool(rate_last["lo"] > 0.5) and full_specific
    h3b = bool(rate_short["hi"] < 0.5)
    out.add("H3", "a", "fetch past a full last page above 50%, and above a short last page", rate_last,
            h3a if est3a else None, estimable=est3a)
    out.add("H3", "b", "fetch after a short first page with more behind it below 50%", rate_short,
            h3b if est3b else None, estimable=est3b)
    gate = "" if uses_count else "not estimable: the row count is not used without a signal"
    sup, est = _combine([(h3a if est3a else None, est3a), (h3b if est3b else None, est3b)])
    out.add("H3", "overall", "row count over signal", {}, sup, estimable=est, note=gate)
    # H3r, formed after the protocol checks: the signal over the row count. Gated the same way: for an
    # agent that never uses the row count, "signal over row count" is vacuous.
    est_r = uses_count and bool(len(signal_last)) and bool(len(signal_more_short))
    sup, est = _combine([(bool(rate_last["hi"] < 0.5) if est_r else None, est_r),
                         (bool(rate_short["lo"] > 0.5) if est_r else None, est_r)])
    out.add("H3r", "overall", "signal over row count: full last page below 50% and short first page above 50%", {},
            sup, estimable=est, note=gate)

    # H4: a false end signal looks like a real last page, so deferring to it is H2a's behavior; its
    # cost is what the amendment tests: more incomplete answers than with no signal on the same rows.
    fa = conflicts[conflicts["conflict"].isin(list(FALSE_END))].assign(incomplete=lambda x: 1.0 - x["evidence_seen"])
    none_more = need[need.signal_form == "none"].assign(incomplete=lambda x: 1.0 - x["evidence_seen"])
    cost = paired(fa, none_more, "incomplete", rng, n_boot=n_boot)
    h4, est4 = bool(cost["p"] < ALPHA and cost["diff"] > 0), bool(cost["n"])
    out.add("H4", "a", "incomplete answers: false end signals - no signal, more rows exist", cost, h4 if est4 else None,
            estimable=est4)
    out.add("H4", "context", "justified correctness: no signal - false end signals",
            paired(none_more, fa, "justified_correct", rng, n_boot=n_boot), None)
    for task in sorted(set(fa["task_type"])):
        out.add("H4", f"by task ({task})", "fetch: no signal - false end signals",
                paired(none_more[none_more.task_type == task], fa[fa.task_type == task], value, rng, n_boot=n_boot), None)
    out.add("H4", "overall", "deferring to a false end signal costs answers (same behavior as H2a)", {},
            h4 if est4 else None, estimable=est4)

    # H6 (formed in amendment 1, before any pilot data): agents act on a contradicting field on the same
    # page. With a false end beside a field that contradicts it, they fetch more than under the same
    # false end alone. (A positive result cannot tell noticing the contradiction from following
    # whichever field says more rows exist.) Pooled over the two pairs (per-item means, sign-flip test); not estimable
    # when fetching under the false ends alone is already above 90%.
    shown_alone = conflicts[conflicts["conflict"].isin(list(VISIBLE.values()))]
    contradicted = conflicts[conflicts["conflict"].isin(list(VISIBLE))]
    for visible, alone in VISIBLE.items():
        out.add("H6", f"by pair ({visible})", f"{visible} - {alone}, more rows exist",
                paired(conflicts[conflicts["conflict"] == visible], conflicts[conflicts["conflict"] == alone], value,
                       rng, n_boot=n_boot), None)
    h6_t = paired(contradicted, shown_alone, value, rng, n_boot=n_boot)
    est6 = bool(h6_t["n"]) and _rate(shown_alone, value) <= BAND[1]
    h6 = bool(h6_t["p"] < ALPHA and h6_t["diff"] > 0)
    out.add("H6", "a", "visible conflicts - the same false ends alone, pooled", h6_t, h6 if est6 else None, estimable=est6)
    out.add("H6", "context", "truthful signals - visible conflicts, more rows exist (how far scrutiny goes)",
            paired(need[need.signal_form.isin(["has_more", "next_cursor"])], contradicted, value, rng, n_boot=n_boot), None)
    out.add("H6", "overall", "agents act on a contradicting field on the same page", {}, h6 if est6 else None, estimable=est6,
            note="" if est6 else "not estimable: fetching under the false ends alone is above 90% or missing")

    # Undocumented interface (amendment 1): the documentation arm without the pagination sentence, on
    # no signal and two forms. A1u is the signal-value test there; H1u and H2u are H1a and H2a there,
    # with the same estimability band. Claims about undocumented APIs rest on these rows.
    undoc = c["fetch"][(c["fetch"]["arm"] == "documentation") & (c["fetch"]["documented"].astype(str) == "False")
                       & (c["fetch"]["task_need"] == "needs_all")]
    u_need, u_last = undoc[undoc["extent"] == "more_full"], undoc[undoc["extent"] == "last_full"]
    tests = [paired(u_need[u_need.signal_form == f], u_last[u_last.signal_form == f], value, rng, n_boot=n_boot)
             for f in UNDOCUMENTED_FORMS]
    sig = holm([t["p"] for t in tests])
    for f, t, s_ in zip(UNDOCUMENTED_FORMS, tests, sig, strict=True):
        out.add("A1u", "a", f"{f}, undocumented: fetch when more rows exist - on a real last page", t,
                bool(s_ and t["diff"] > 0) if t["n"] else None, estimable=bool(t["n"]))
    est_u = all(t["n"] for t in tests)
    a1u = all(s_ and t["diff"] > 0 for t, s_ in zip(tests, sig, strict=True))
    out.add("A1u", "overall", "signal value without the pagination cue", {}, a1u if est_u else None, estimable=est_u)
    pu_need, pu_last = _rate(u_need[u_need.signal_form == "none"], value), _rate(u_last[u_last.signal_form == "none"], value)
    est_h1u = bool(pu_need <= BAND[1]) and all((u_need.signal_form == f).any() for f in UNDOCUMENTED_FORMS)
    h1u = _contrasts(out, rng, n_boot, "H1u", "a", [(f, "none") for f in UNDOCUMENTED_FORMS], u_need,
                     "undocumented, fetch when needed", value)
    out.add("H1u", "overall", f"H1a without the pagination cue; no-signal rate {pu_need:.2f}", {},
            h1u if est_h1u else None, estimable=est_h1u,
            note="" if est_h1u else f"not estimable: {_why_not(u_need, UNDOCUMENTED_FORMS, pu_need, low=False)}")
    est_h2u = bool(pu_last >= BAND[0]) and all((u_last.signal_form == f).any() for f in UNDOCUMENTED_FORMS)
    h2u = _contrasts(out, rng, n_boot, "H2u", "a", [("none", f) for f in UNDOCUMENTED_FORMS], u_last,
                     "undocumented, fetch past a full last page", value)
    out.add("H2u", "overall", f"H2a without the pagination cue; no-signal rate {pu_last:.2f}", {},
            h2u if est_h2u else None, estimable=est_h2u,
            note="" if est_h2u else f"not estimable: {_why_not(u_last, UNDOCUMENTED_FORMS, pu_last, low=True)}")

    # Context for H5b, from every episode before any hand-label filter: does the field itself change
    # how often answers are incomplete in the warranted cells?
    everyone = matched_pairs(d)
    everyone = everyone[everyone["conflict"].isin(_NO_CONFLICT) & (everyone["extent"] == "more_full")]
    out.add("H5b", "context", "incompleteness: with the field - without, warranted cells",
            paired(everyone.assign(v=(everyone["evidence_seen_with"] == 0).astype(float)),
                   everyone.assign(v=(everyone["evidence_seen_without"] == 0).astype(float)), "v", rng, n_boot=n_boot),
            None)

    # H5a where disclosure is warranted from the agent's point of view; the other strata are reported.
    # Estimable from 16 items: with fewer, even zero disclosures cannot bring the bound below 20%.
    dd, source = _prose(d, validation)
    incomplete = dd[(dd["task_need"] == "needs_all") & (dd["evidence_seen"] == 0) & (dd["answer_format"] == "final_line")]
    warranted = incomplete[incomplete["disclosure_stratum"] == "warranted"]
    stats = _item_wilson(warranted["prose_disclosed"], warranted["key"])
    est5a = bool(stats["n"] >= MIN_ITEMS_H5A)
    h5a = bool(stats["hi"] < RARE) if est5a else None
    note = "" if est5a else f"not estimable: {stats['n']} warranted items, fewer than {MIN_ITEMS_H5A}"
    out.add("H5a", "a", f"disclosure where warranted, upper 95% bound < 20%; {source}", stats, h5a, estimable=est5a,
            note=note)
    for stratum in ["api_said_done", "visible_conflict", "short_page", "no_cue"]:
        g = incomplete[incomplete["disclosure_stratum"] == stratum]
        out.add("H5a", f"stratum ({stratum})", "disclosure rate (descriptive)", _item_wilson(g["prose_disclosed"], g["key"]),
                None)
    out.add("H5a", "overall", "where warranted", {}, h5a, estimable=est5a, note=note)

    # H5b in the warranted cells (no signal, or a truthful has_more, on a full page with more rows):
    # (a) intention to treat over all matched pairs, outcome = an incomplete answer that does not say so;
    # (b) the field must be informative where incompleteness is most likely, the no-signal cell: with it,
    # disclosure is more frequent on incomplete answers than on complete ones, so neither a reflexive
    # "unknown" nor a rule like "partial whenever no signal is shown" passes. Each part needs 10 items
    # whose outcome can vary.
    dd = dd.assign(disclosed_any=(dd["prose_disclosed"].astype(bool)
                                  | dd["stated_completeness"].isin(["partial", "unknown"])).astype(float))
    dd = dd.assign(silent_incomplete=((dd["evidence_seen"] == 0) & (dd["disclosed_any"] == 0)).astype(float))
    pairs = matched_pairs(dd)
    pairs = pairs[pairs["conflict"].isin(_NO_CONFLICT) & (pairs["extent"] == "more_full")]
    itt = paired(pairs.assign(v=pairs["silent_incomplete_without"]), pairs.assign(v=pairs["silent_incomplete_with"]),
                 "v", rng, n_boot=n_boot)
    varying = pairs.loc[(pairs["evidence_seen_with"] == 0) | (pairs["evidence_seen_without"] == 0), "key"].nunique()
    est5b_a = bool(varying >= MIN_ITEMS_H5B)
    h5b_a = bool(itt["p"] < ALPHA and itt["diff"] > 0)
    out.add("H5b", "a", f"silent incomplete answers: without the field - with it, warranted cells; {source}", itt,
            h5b_a if est5b_a else None, estimable=est5b_a,
            note="" if est5b_a else f"not estimable: {varying} items with an incomplete answer, fewer than {MIN_ITEMS_H5B}")
    fallback = validation is not None and not validation["use_flag"]
    if fallback:
        # The labeled pairs are drawn from those with an incomplete answer in either format (pairs where both
        # answers are complete differ by zero), so the difference over every warranted pair is estimated as the
        # labeled difference times the share of pairs that can differ, known without labels (changelog, 23 Oct 2026).
        every = matched_pairs(d)
        every = every[every["conflict"].isin(_NO_CONFLICT) & (every["extent"] == "more_full")]
        share = float(((every["evidence_seen_with"] == 0) | (every["evidence_seen_without"] == 0)).mean()) \
            if len(every) else np.nan
        out.add("H5b", "a (rescaled)", f"the same over every warranted pair: labeled difference x {share:.2f}, the "
                "share of pairs with an incomplete answer (descriptive)",
                {**itt, **{k: itt[k] * share for k in ("diff", "lo", "hi")}}, None)
    # Under the hand-label fallback, the labeling sample holds about 10 field replies per model in the no-signal
    # cell, too few for (b)'s minimum, so (b) reads disclosure from the COMPLETENESS line alone, on every
    # episode, which needs no label; the version on labeled episodes is reported beside it (changelog, 23 Oct 2026).
    line_only = d.assign(disclosed_any=d["stated_completeness"].isin(["partial", "unknown"]).astype(float))
    with_field, gaps = _informativeness(line_only if fallback else dd, rng, n_boot)
    gap, n_inc, n_com = gaps["none"]
    est5b_b = bool(n_inc >= MIN_ITEMS_H5B and n_com >= MIN_ITEMS_H5B)
    h5b_b = bool(np.isfinite(gap["lo"]) and gap["lo"] > 0)
    how = "; COMPLETENESS line only, every episode (hand-label fallback)" if fallback else ""
    out.add("H5b", "b", f"with the field, no signal: disclosure on incomplete - on complete answers (informativeness){how}",
            gap, h5b_b if est5b_b else None, estimable=est5b_b,
            note="" if est5b_b else f"not estimable: {n_inc} items incomplete, {n_com} complete (need {MIN_ITEMS_H5B} each)")
    out.add("H5b", "descriptive", "with the field, truthful has_more: disclosure on incomplete - on complete answers",
            gaps["has_more"][0], None)
    if fallback:
        _, labeled = _informativeness(dd, rng, n_boot)
        lgap, l_inc, l_com = labeled["none"]
        l_est = bool(l_inc >= MIN_ITEMS_H5B and l_com >= MIN_ITEMS_H5B)
        out.add("H5b", "b (labeled episodes)", f"the same on labeled episodes, prose or the line; {source}", lgap, None,
                estimable=l_est, note="" if l_est else f"not estimable: {l_inc} items incomplete, {l_com} complete "
                f"(need {MIN_ITEMS_H5B} each)")
    complete = with_field[with_field["evidence_seen"] == 1]
    out.add("H5b", "context (false alarms)", "with the field: partial/unknown on complete answers",
            _item_wilson(complete["stated_completeness"].isin(["partial", "unknown"]), complete["key"]), None)
    sup, est = _combine([(h5b_a if est5b_a else None, est5b_a), (h5b_b if est5b_b else None, est5b_b)])
    out.add("H5b", "overall", "a and b", {}, sup, estimable=est)
    return out.rows


def _informativeness(d: pd.DataFrame, rng, n_boot) -> tuple[pd.DataFrame, dict]:
    """H5b(b): in the warranted cells with the completeness field, disclosure (`disclosed_any`) on incomplete
    minus on complete answers, per form (no signal, truthful has_more), with the items on each side."""
    with_field = d[(d["answer_format"] == "completeness") & d["conflict"].isna() & (d["task_need"] == "needs_all")
                   & (d["extent"] == "more_full")]
    gaps = {}
    for form in ["none", "has_more"]:
        cell = with_field[with_field.signal_form == form]
        inc, com = cell[cell["evidence_seen"] == 0], cell[cell["evidence_seen"] == 1]
        gaps[form] = (_cluster_gap(inc, com, "disclosed_any", rng, n_boot), inc["key"].nunique(), com["key"].nunique())
    return with_field, gaps


def _contrasts_across(out: _Rows, rng, n_boot, need, last, value) -> tuple[bool, bool]:
    """A1: for each form, fetch when more rows exist minus fetch on a real last page, paired by item.
    Returns (supported, estimable); not estimable when any form has no paired items."""
    tests = [paired(need[need.signal_form == f], last[last.signal_form == f], value, rng, n_boot=n_boot)
             for f in MAIN_EXPLICIT]
    sig = holm([t["p"] for t in tests])
    for f, t, s in zip(MAIN_EXPLICIT, tests, sig, strict=True):
        out.add("A1", "a", f"{f}: fetch when more rows exist - fetch on a real last page", t,
                bool(s and t["diff"] > 0) if t["n"] else None, estimable=bool(t["n"]))
    out.add("A1", "reference", "none: the same difference (zero in expectation: nothing on the page tells the extents apart)",
            paired(need[need.signal_form == "none"], last[last.signal_form == "none"], value, rng, n_boot=n_boot), None)
    return all(s and t["diff"] > 0 for t, s in zip(tests, sig, strict=True)), all(t["n"] for t in tests)


def descriptive_tests(d: pd.DataFrame, n_boot: int, seed: int) -> list[dict]:
    """Each one-factor arm against its base cell (same extent and task need), on fetching. The
    answer-format arm's base is the same form with the final-line format."""
    rng = np.random.default_rng(seed)
    out = _Rows("descriptive")
    fetch = d[(d["settled_on_page1"] == 0) & (d["own_small_page"] == 0)]
    for arm, (label, base_form) in DESCRIPTIVE_ARMS.items():
        cells = fetch[fetch["arm"] == arm]
        for (extent, task_need, form), a in cells.groupby(["extent", "task_need", "signal_form"]):
            b = fetch[(fetch["arm"] == "core") & (fetch["answer_format"] == "final_line")
                      & (fetch.signal_form == (base_form or form)) & (fetch["extent"] == extent)
                      & (fetch["task_need"] == task_need)]
            out.add("arms", arm, f"{label} ({form}) - base, fetch ({extent}, {task_need})",
                    paired(a, b, "follow_up", rng, n_boot=n_boot), None)
    return out.rows


def _overall(detail: pd.DataFrame, family: str, confirmatory: list[str] | None) -> pd.DataFrame:
    rows = detail[(detail["family"] == family) & (detail["part"] == "overall")]
    table = rows.pivot_table(index="hypothesis", columns="model", values="supported", aggfunc="first", dropna=False)
    counted = confirmatory or list(table.columns)
    present = [m for m in counted if m in table]
    if family == "registered":
        # As registered: a missing or failing model counts as not supporting.
        support = table[present].fillna(False).astype(bool) if present else table.iloc[:, :0]
        table = table.astype(object)
        table["models_supporting"] = support.sum(axis=1).astype(int) if present else 0
        table["supported_overall"] = table["models_supporting"] >= len(counted) // 2 + 1
        return table
    # Amended: a majority of the confirmatory models where the test is estimable, with at least two.
    est = rows.pivot_table(index="hypothesis", columns="model", values="estimable", aggfunc="first")
    table = table.astype(object)
    n_est = est[present].fillna(False).astype(bool).sum(axis=1) if present else 0
    n_sup = table[present].apply(lambda r: sum(v is True or v == 1.0 for v in r), axis=1) if present else 0
    table["models_estimable"] = n_est
    table["models_supporting"] = n_sup
    table["supported_overall"] = [
        ("not estimable" if e < 2 else bool(s >= e // 2 + 1)) for s, e in zip(table["models_supporting"],
                                                                             table["models_estimable"], strict=True)]
    return table


SENSITIVITIES = {
    "empty replies kept as stops": {"empty_as_stop": True},
    "without the oldest-date task": {"exclude_tasks": ["oldest_date"]},
    "without the export task": {"exclude_tasks": ["export_all"]},
    "responsive follow-ups only": {"value": "responsive_follow_up"},
}


def run(df: pd.DataFrame, n_boot: int = 2000, seed: int = 0, confirmatory: list[str] | None = None,
        labels: pd.DataFrame | None = None, empty_as_stop: bool = False, exclude_tasks: list[str] | None = None,
        value: str = "follow_up", families: tuple[str, ...] = ("registered", "amended", "descriptive"),
        ) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Every test per model, and the overall verdict per family."""
    d = analysis_sample(df, empty_as_stop)
    if exclude_tasks:
        d = d[~d["task_type"].isin(exclude_tasks)]
    validation = validate_flag(labels, df) if labels is not None else None
    rows = []
    for model, g in d.groupby("model"):
        if "registered" in families:
            rows += [{"model": model, **r} for r in registered_tests(g, n_boot, seed, validation)]
        if "amended" in families:
            rows += [{"model": model, **r} for r in amended_tests(g, n_boot, seed, validation, value)]
        if "descriptive" in families:
            rows += [{"model": model, **r} for r in descriptive_tests(g, n_boot, seed)]
    detail = pd.DataFrame(rows)
    overall = {f: _overall(detail, f, confirmatory) for f in families if f != "descriptive" and len(detail)}
    return detail, overall


def confirmatory_models(config: str) -> list[str] | None:
    """The models of the given run config; "none" counts every model in the data."""
    if config == "none":
        return None
    if not Path(config).exists():
        sys.exit(f"{config} not found: run from the repository root, or pass --config none to count every model")
    from fplp.config import load_run_config

    return load_run_config(config).get("models") or None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv")
    parser.add_argument("--out", help="optional CSV of every test (sensitivity analyses go to <out>_<name>.csv)")
    parser.add_argument("--config", default="configs/runs/main.yaml",
                        help="run config whose models are the confirmatory set (default: the main study); "
                        "`none` counts every model in the data")
    parser.add_argument("--disclosure-labels", help="consensus labels from `fplp disclosure check`; if the "
                        "flag's precision or recall is below 0.80, H5 uses the hand labels")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    df = pd.read_csv(args.scored_csv)
    labels = pd.read_csv(args.disclosure_labels) if args.disclosure_labels else None
    confirmatory = confirmatory_models(args.config)
    detail, overall = run(df, args.n_boot, args.seed, confirmatory, labels)
    counted = confirmatory or sorted(df["model"].unique())
    if confirmatory is None:
        print("NOTE: no confirmatory set (--config none). The H rows below are descriptive, not tests of "
              "the pre-registered hypotheses, which use the main study only.\n")
    # As registered, every test is repeated with empty replies kept as stops (both families); the other
    # sensitivity analyses were added by amendment 1 and cover the amended family.
    sensitivity = {name: run(df, args.n_boot, args.seed, confirmatory, labels,
                             families=("registered", "amended") if kw.get("empty_as_stop") else ("amended",), **kw)
                   for name, kw in SENSITIVITIES.items()}
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 90):
        print("Exclusions (empty replies and refusals are excluded; truncation and the cap are reported):")
        print(exclusion_table(df).to_string(index=False))
        reliability = retest_reliability(df)
        if len(reliability):
            print("\nRetest reliability (a random 10% of conditions run twice; not used by any test):")
            print(reliability.round(3).to_string(index=False))
        print()
        print(detail.drop(columns=["method"]).round(3).to_string(index=False))
        print(f"\nRegistered verdicts (supported in at least {len(counted) // 2 + 1} of {len(counted)} confirmatory "
              f"models: {', '.join(counted)}):")
        print(overall["registered"].to_string())
        print("\nAmended verdicts (supported in a majority of the confirmatory models where the test is estimable, "
              "with at least two):")
        print(overall["amended"].to_string())
        for name, (_, sens) in sensitivity.items():
            if "registered" in sens:
                print(f"\nSensitivity, registered verdicts, {name}:")
                print(sens["registered"][["models_supporting", "supported_overall"]].to_string())
            print(f"\nSensitivity, amended verdicts, {name}:")
            print(sens["amended"][["models_estimable", "models_supporting", "supported_overall"]].to_string())
    if args.out:
        out = Path(args.out)
        detail.to_csv(out, index=False)
        retest_reliability(df).to_csv(out.with_name(f"{out.stem}_retest{out.suffix}"), index=False)
        for name, (sdetail, _) in sensitivity.items():
            slug = name.replace(" ", "_").replace("-", "_")
            sdetail.to_csv(out.with_name(f"{out.stem}_{slug}{out.suffix}"), index=False)


if __name__ == "__main__":
    main()
