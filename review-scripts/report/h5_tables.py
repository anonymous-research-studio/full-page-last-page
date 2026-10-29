"""Markdown tables of H5 on the hand labels, in the format of REVIEW/results_provisional.md (gen.py's).

  python h5_tables.py <scratch checkout at 1b7f776> <main_hypotheses.csv with labels> > fragment.md

Rows come from the frozen `fplp hypotheses --disclosure-labels` output; across-model verdicts from the frozen
`_overall`. Status: "final (hand labels)" for rows that read the labels or the COMPLETENESS line under the
fallback, "final" for the incompleteness context rows (mechanical)."""
import math
import sys
from pathlib import Path

import pandas as pd

A, CSV = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(A / "src"))
from fplp.analysis.hypotheses import _overall  # noqa: E402

CONF = ["gpt-oss-120b", "mistral-medium-3-5", "claude-sonnet-5-5"]
SHORT = {"gpt-oss-120b": "gpt-oss", "mistral-medium-3-5": "Mistral", "claude-sonnet-5-5": "Claude"}


def status(r):
    if str(r["part"]).startswith("context") and "incompleteness" in str(r["test"]):
        return "final"
    return "final (hand labels)"


def is_rate(t): return " - " not in t and "labeled difference" not in t
def nan(x): return x is None or (isinstance(x, float) and math.isnan(x))
def fval(v, t): return "–" if nan(v) else (f"{100 * v:.1f}%" if is_rate(t) else f"{100 * v:+.1f}")
def fci(lo, hi, t):
    if nan(lo) or nan(hi): return "–"
    lvl = "90%" if "(90% CI)" in t else "95%"
    return f"{lvl} [{100 * lo:.1f}, {100 * hi:.1f}]" if is_rate(t) else f"{lvl} [{100 * lo:+.1f}, {100 * hi:+.1f}]"
def fp(p): return "–" if nan(p) else ("<.001" if p < 0.001 else f"{p:.3f}")


def method(r):
    m = r.get("method")
    if isinstance(m, str):
        return {"McNemar exact; Agresti-Min CI": "McNemar exact; Agresti-Min",
                "sign-flip permutation; bootstrap CI": "sign-flip; bootstrap"}.get(m, m)
    t, h = str(r["test"]), str(r["hypothesis"])
    if r["part"] == "overall": return ""
    if h in ("H5", "H5a") or "partial/unknown" in t: return "Wilson, each item once"
    if "informativeness" in t or "disclosure on incomplete - on complete" in t: return "bootstrap over items"
    return "–"


def decision(r):
    s, e = str(r["supported"]), str(r["estimable"])
    if r["part"] == "overall":
        if e == "False": return "**not estimable**"
        return {"True": "**supported**", "False": "**not supported**"}.get(s, "–")
    if e == "False": return "not estimable"
    return {"True": "passes", "False": "fails"}.get(s, "reported")


df = pd.read_csv(CSV)
df = df[df["model"].isin(CONF) & df["hypothesis"].isin(["H5", "H5a", "H5b"])]
out = []
for fam in ("registered", "amended"):
    d = df[df["family"] == fam]
    for hyp in dict.fromkeys(d["hypothesis"]):
        h = d[d["hypothesis"] == hyp]
        out += [f"\n#### {fam.capitalize()} {hyp}, hand labels\n",
                "| Model | Part | Test | n | Estimate (pts or %) | CI | p | Method | Decision | Status |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for m in CONF:
            for _, r in h[h["model"] == m].iterrows():
                n = "" if pd.isna(r["n"]) else f"{int(r['n'])}"
                note = f" ({r['note']})" if isinstance(r.get("note"), str) else ""
                out.append(f"| {SHORT[m]} | {r['part']} | {r['test']}{note} | {n} | {fval(r['diff'], r['test'])} | "
                           f"{fci(r['lo'], r['hi'], r['test'])} | {fp(r['p'])} | {method(r)} | {decision(r)} | {status(r)} |")
print("\n".join(out))
full = pd.read_csv(CSV)
for fam in ("registered", "amended"):
    ov = _overall(full, fam, CONF)
    print(f"\nAcross models, {fam} (frozen `_overall`):\n")
    print(ov[ov.index.isin(["H5", "H5a", "H5b"])].to_string())
