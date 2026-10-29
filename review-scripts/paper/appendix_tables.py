"""Rows for two appendix tables, from the frozen results (no number typed by hand):
  h4task_rows.tex   amended H4 by task (post hoc): incomplete answers, false ends minus no signal
  posthoc_rows.tex  self-contradicting page minus the contradicting field alone, same rows (post hoc)
Run with the frozen code on PYTHONPATH:  python appendix_tables.py <results-2026-10-25 dir> <out dir>"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, paired
from fplp.analysis.hypotheses import _cells

R, out = Path(sys.argv[1]), Path(sys.argv[2])
M = ["gpt-oss-120b", "mistral-medium-3-5", "claude-sonnet-5-5"]
TASKS = {"count_high_priority": "High-priority count", "count_out_of_stock": "Out-of-stock count", "exists": "Exists",
         "export_all": "Export", "filtered_count": "Filtered count", "oldest_date": "Oldest date"}
def pp(d, lo, hi, nd=0):
    return f"{100 * d:+.{nd}f} [{100 * lo:+.{nd}f}, {100 * hi:+.{nd}f}]".replace("-", "$-$")

t = pd.read_csv(R / "tables" / "posthoc_h4_incomplete_by_task.csv")
lines = []
for task, name in TASKS.items():
    cells = []
    for m in M:
        r = t[(t.model == m) & (t.task == task)].iloc[0]
        if r["diff"] == 0 and r["lo"] == 0 and r["hi"] == 0:
            cells.append(f"0 (both {100 * r['incomplete_no_signal']:.0f}\\%)")
        else:
            cells.append(pp(r["diff"], r["lo"], r["hi"]))
    lines.append(f"{name} & " + " & ".join(cells) + r" \\")
(out / "h4task_rows.tex").write_text("\n".join(lines) + "\n")

s = pd.read_csv(R / "processed" / "main.csv", low_memory=False)
cells = {m: _cells(g, own_small_page=True) for m, g in analysis_sample(s).groupby("model")}
rng = np.random.default_rng(0)
NAMES = {"gpt-oss-120b": "gpt-oss-120b", "mistral-medium-3-5": "Mistral Medium 3.5", "claude-sonnet-5-5": "Claude Sonnet 5.5"}
lines = []
for m in M:
    row = []
    for vc, form in [("visible_conflict_total", "total_count"), ("visible_conflict_note", "nl_note_json")]:
        a = cells[m]["conflicts"][cells[m]["conflicts"].conflict == vc]
        b = cells[m]["need"][cells[m]["need"].signal_form == form]
        r = paired(a, b, "follow_up", rng)
        p = "$p<.001$" if r["p"] < 0.001 else f"$p={r['p']:.2f}$".replace("0.", ".")
        row.append(f"{100 * a.follow_up.mean():.0f} vs {100 * b.follow_up.mean():.0f}; {pp(r['diff'], r['lo'], r['hi'], 1)}, {p}")
    lines.append(f"{NAMES[m]} & " + " & ".join(row) + r" \\")
(out / "posthoc_rows.tex").write_text("\n".join(lines) + "\n")
print((out / "h4task_rows.tex").read_text()); print((out / "posthoc_rows.tex").read_text())
