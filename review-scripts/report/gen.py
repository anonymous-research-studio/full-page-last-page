"""Build the tables of REVIEW/results_provisional.md from the frozen pipeline's CSVs.

Every number comes from the CSVs; the across-model verdicts use the frozen code's own `_overall`.
Writes one markdown fragment per placeholder into OUT_DIR; assemble.py fills the template."""

import math
import sys
from pathlib import Path

import pandas as pd

A = Path(sys.argv[1])          # the scratch checkout at 1b7f776, with results/tables
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(A / "src"))
from fplp.analysis.hypotheses import _overall  # noqa: E402

T = A / "results" / "tables"
CONF = ["gpt-oss-120b", "mistral-medium-3-5", "claude-sonnet-5-5"]
SHORT = {"gpt-oss-120b": "gpt-oss", "mistral-medium-3-5": "Mistral", "claude-sonnet-5-5": "Claude",
         "nemotron-3-super": "Nemotron"}
FINAL, PC, PD = "final", "PROVISIONAL (correctness)", "PROVISIONAL (disclosure validation)"


def status(r, nemotron=False) -> str:
    test, part, hyp = str(r["test"]), str(r["part"]), str(r["hypothesis"])
    if "correct" in test:
        return PC + (", not audited: Nemotron is outside the audit" if nemotron else "")
    disclosure_hyp = hyp in ("H5", "H5a", "H5b")
    if disclosure_hyp and not (part.startswith("context") and "incompleteness" in test):
        return PD
    return FINAL


def is_rate(test: str) -> bool:
    return " - " not in test


def fmt_val(v, test):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    return f"{100 * v:.1f}%" if is_rate(test) else f"{100 * v:+.1f}"


def fmt_ci(lo, hi, test):
    if any(x is None or (isinstance(x, float) and math.isnan(x)) for x in (lo, hi)):
        return "–"
    level = "90%" if "(90% CI)" in test else "95%"
    if is_rate(test):
        return f"{level} [{100 * lo:.1f}, {100 * hi:.1f}]"
    return f"{level} [{100 * lo:+.1f}, {100 * hi:+.1f}]"


def fmt_p(p):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "–"
    return "<.001" if p < 0.001 else f"{p:.3f}"


def method(r) -> str:
    m = r.get("method")
    if isinstance(m, str):
        return {"McNemar exact; Agresti-Min CI": "McNemar exact; Agresti-Min",
                "sign-flip permutation; bootstrap CI": "sign-flip; bootstrap"}.get(m, m)
    test, hyp = str(r["test"]), str(r["hypothesis"])
    if r["part"] == "overall":
        return ""
    if hyp == "H3":
        return "bootstrap over items (rate)"
    if hyp in ("H5", "H5a") or "partial/unknown" in test:
        return "Wilson, each item once"
    if "informativeness" in test or "disclosure on incomplete - on complete" in test:
        return "bootstrap over items"
    return "–"


def decision(r) -> str:
    s, e = r["supported"], r["estimable"]
    if r["part"] == "overall":
        if e is False or str(e) == "False":
            return "**not estimable**"
        return {True: "**supported**", False: "**not supported**"}.get(s if isinstance(s, bool) else
                                                                      {"True": True, "False": False}.get(str(s)), "–")
    if str(e) == "False":
        return "not estimable"
    return {"True": "passes", "False": "fails"}.get(str(s), "reported")


def detail_tables(df: pd.DataFrame, family: str, models: list[str], nemotron=False) -> str:
    out = []
    d = df[df["family"] == family]
    for hyp in dict.fromkeys(d["hypothesis"]):
        h = d[d["hypothesis"] == hyp]
        out.append(f"\n#### {family.capitalize()} {hyp}\n")
        out.append("| Model | Part | Test | n | Estimate (pts or %) | CI | p | Method | Decision | Status |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for m in models:
            for _, r in h[h["model"] == m].iterrows():
                n = "" if pd.isna(r["n"]) else f"{int(r['n'])}"
                note = f" ({r['note']})" if isinstance(r.get("note"), str) else ""
                ff = r.get("fetch_under_false")
                extra = f"; fetching under the false signals {100 * ff:.1f}%" if isinstance(ff, float) and not math.isnan(ff) else ""
                out.append(f"| {SHORT[m]} | {r['part']} | {r['test']}{note}{extra} | {n} | {fmt_val(r['diff'], r['test'])} | "
                           f"{fmt_ci(r['lo'], r['hi'], r['test'])} | {fmt_p(r['p'])} | {method(r)} | {decision(r)} | "
                           f"{status(r, nemotron)} |")
    return "\n".join(out) + "\n"


def verdict_table(df: pd.DataFrame, family: str, models: list[str], conf) -> tuple[str, pd.DataFrame]:
    t = _overall(df, family, conf)
    cols = [m for m in models if m in t.columns]
    head = ["Hypothesis", *[SHORT[m] for m in cols]]
    if family == "amended" and conf:
        head += ["models estimable", "models supporting", "overall"]
    elif conf:
        head += ["models supporting", "overall (≥2 of 3)"]
    lines = ["| " + " | ".join(head + ["Status"]) + " |", "|" + "---|" * (len(head) + 1)]
    word = lambda v: {True: "supported", False: "not supported"}.get(v if isinstance(v, bool) else
                                                                    {"True": True, "False": False}.get(str(v)), "not estimable")
    for hyp, r in t.iterrows():
        cells = [hyp, *[word(r[m]) for m in cols]]
        if family == "amended" and conf:
            cells += [str(r["models_estimable"]), str(r["models_supporting"]), str(r["supported_overall"])]
        elif conf:
            cells += [str(r["models_supporting"]), str(r["supported_overall"])]
        st = PD if hyp in ("H5", "H5a", "H5b") else FINAL
        lines.append("| " + " | ".join(cells + [st]) + " |")
    return "\n".join(lines) + "\n", t


main = pd.read_csv(T / "main_hypotheses.csv")
frag = {}
frag["VERDICTS_REGISTERED"], reg = verdict_table(main, "registered", CONF, CONF)
frag["VERDICTS_AMENDED"], amd = verdict_table(main, "amended", CONF, CONF)
frag["DETAIL_REGISTERED"] = detail_tables(main, "registered", CONF)
frag["DETAIL_AMENDED"] = detail_tables(main, "amended", CONF)
frag["DETAIL_ARMS"] = detail_tables(main, "descriptive", CONF)

# Sensitivities and the second scoring: overall verdicts side by side with the primary analysis.
sens = {"primary (registered scoring)": main}
for name, f in [("empty replies kept as stops", "main_hypotheses_empty_replies_kept_as_stops.csv"),
                ("without the oldest-date task", "main_hypotheses_without_the_oldest_date_task.csv"),
                ("without the export task", "main_hypotheses_without_the_export_task.csv"),
                ("responsive follow-ups only", "main_hypotheses_responsive_follow_ups_only.csv"),
                ("second scoring (`--fixes`, not registered)", "main_fixed_hypotheses.csv")]:
    sens[name] = pd.read_csv(T / f)
names = list(sens)
lines = ["| Family | Hypothesis | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
for fam in ("registered", "amended"):
    tabs = {name: _overall(df, fam, CONF) for name, df in sens.items() if fam in set(df["family"])}
    for hyp in tabs["primary (registered scoring)"].index:
        cells = []
        for name in names:
            t = tabs.get(name)
            if t is None or hyp not in t.index:
                cells.append("– (not computed)")
                continue
            r = t.loc[hyp]
            est = f"/{r['models_estimable']}" if "models_estimable" in r else "/3"
            cells.append(f"{r['supported_overall']} ({r['models_supporting']}{est})")
        lines.append(f"| {fam} | {hyp} | " + " | ".join(cells) + " |")
frag["SENSITIVITY"] = "\n".join(lines) + "\n\nEach cell: overall verdict (models supporting / models counted: 3 for registered, estimable for amended).\n"

# Retest reliability (a random 10% of conditions run twice; no test uses it).
def retest_table(path: Path) -> str:
    rt = pd.read_csv(path)
    lines = ["| Model | Outcome | Pairs | Agreement | Cohen's κ | Rate, first run | Rate, retest | Status |",
             "|---|---|---|---|---|---|---|---|"]
    for _, r in rt.iterrows():
        st = PC if r["outcome"] == "correct" else (PD if r["outcome"] == "disclosure_flag" else FINAL)
        kappa = "–" if pd.isna(r["kappa"]) else f"{r['kappa']:.3f}"
        lines.append(f"| {SHORT[r['model']]} | {r['outcome']} | {int(r['pairs'])} | {100 * r['agreement']:.1f}% | {kappa} | "
                     f"{100 * r['rate_first']:.1f}% | {100 * r['rate_retest']:.1f}% | {st} |")
    return "\n".join(lines) + "\n"


frag["RETEST"] = retest_table(T / "main_hypotheses_retest.csv")
frag["NEMOTRON_RETEST"] = retest_table(T / "exploratory_hypotheses_retest.csv")

# Nemotron, exploratory: per-model columns only.
nem = pd.read_csv(T / "exploratory_hypotheses.csv")
frag["NEMOTRON_REGISTERED"], _ = verdict_table(nem, "registered", ["nemotron-3-super"], None)
frag["NEMOTRON_AMENDED"], _ = verdict_table(nem, "amended", ["nemotron-3-super"], None)
frag["NEMOTRON_DETAIL"] = (detail_tables(nem, "registered", ["nemotron-3-super"], True)
                           + detail_tables(nem, "amended", ["nemotron-3-super"], True))

# Robustness (amendment 2, gpt-oss only).
rb = pd.read_csv(T / "robustness.csv")
lines = ["| Check | Test | Rate A | Rate B | n | Difference (pts) | 95% CI | p |", "|---|---|---|---|---|---|---|---|"]
for _, r in rb.iterrows():
    lines.append(f"| {r['check']} | {r['test']} | {100 * r['rate_a']:.1f}% | {100 * r['rate_b']:.1f}% | {int(r['n'])} | "
                 f"{100 * r['diff']:+.1f} | [{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}] | {fmt_p(r['p'])} |")
frag["ROBUSTNESS"] = "\n".join(lines) + "\n"

# Logistic regression (descriptive).
mf = pd.read_csv(T / "main_model_fixed.csv").round(3)
frag["MODEL"] = "\n".join(["| " + " | ".join(map(str, mf.columns)) + " |", "|" + "---|" * len(mf.columns)]
                          + ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in mf.itertuples(index=False)]) + "\n"

# Secondary conditions (gpt-oss only, descriptive arms and false_more).
sec = pd.read_csv(T / "secondary_hypotheses.csv")
keep = sec[(sec["family"] == "descriptive") | sec["test"].str.contains("false_more")]
lines = ["| Part | Test | n | Difference (pts) | 95% CI | p | Method |", "|---|---|---|---|---|---|---|"]
for _, r in keep.iterrows():
    lines.append(f"| {r['part']} | {r['test']} | {int(r['n'])} | {fmt_val(r['diff'], r['test'])} | "
                 f"{fmt_ci(r['lo'], r['hi'], r['test'])} | {fmt_p(r['p'])} | {method(r)} |")
frag["SECONDARY"] = "\n".join(lines) + "\n"

for k, v in frag.items():
    (OUT / f"{k}.md").write_text(v)

# Cross-check against the frozen run's printed verdicts.
print(reg[["models_supporting", "supported_overall"]].to_string())
print(amd[["models_estimable", "models_supporting", "supported_overall"]].to_string())
print("rows by status:", main.apply(status, axis=1).value_counts().to_dict())
print("correctness rows:", main[main.apply(status, axis=1) == PC][["model", "hypothesis", "part", "test"]].to_string(index=False))
