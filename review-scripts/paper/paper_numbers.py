"""Numbers for REVIEW/paper-fill.md that the per-test CSV does not hold, computed with the frozen
analysis code's own cell filters (commit 1b7f776, via PYTHONPATH) on the frozen scoring of the main study.
Run: PYTHONPATH=<1b7f776 checkout>/src python paper_numbers.py <results-2026-10-25 dir>"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fplp.analysis.common import analysis_sample, paired
from fplp.analysis.hypotheses import FALSE_END, _cells

R = Path(sys.argv[1])
s = pd.read_csv(R / "processed" / "main.csv", low_memory=False)
M = ["gpt-oss-120b", "mistral-medium-3-5", "claude-sonnet-5-5"]
cells = {m: _cells(g, own_small_page=True) for m, g in analysis_sample(s).groupby("model")}
rng = np.random.default_rng(0)
pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731


def head(t):
    print(f"\n### {t}")


head("A. Episodes and exclusions (main study)")
for m in M:
    g = s[s.model == m]
    print(m, "episodes", len(g), "| design", int((g.arm != "retest").sum()), "| retests", int((g.arm == "retest").sum()),
          "| empty", int(g.empty_reply.sum()), "| refusals", int((g.stop_reason == "refusal").sum()),
          "| truncated", int(g.truncated.sum()), "| hit cap", int(g.hit_cap.sum()),
          "| cap hits outside retests", int(g[g.arm != "retest"].hit_cap.sum()))

head("B. No-signal fetch when more rows exist, by task (need cell)")
for m in M:
    n = cells[m]["need"]
    n = n[n.signal_form == "none"]
    print(m, "all", pct(n.follow_up.mean()), "|", ", ".join(f"{t} {pct(v)}" for t, v in n.groupby("task_type").follow_up.mean().sort_values().items()))

head("C. Page-1-sufficient tasks (H2b cell): fetch rate by form")
for m in M:
    p = cells[m]["page1"]
    print(m, ", ".join(f"{f} {pct(v)}" for f, v in p.groupby("signal_form").follow_up.mean().items()), "| n per form", p.groupby("signal_form").size().iloc[0])

head("D. Post hoc: self-contradicting page minus the contradicting field alone (truthful form, same rows)")
for m in M:
    c, n = cells[m]["conflicts"], cells[m]["need"]
    for vc, form in [("visible_conflict_total", "total_count"), ("visible_conflict_note", "nl_note_json")]:
        a, b = c[c.conflict == vc], n[n.signal_form == form]
        t = paired(a, b, "follow_up", rng)
        print(m, f"{vc} {pct(a.follow_up.mean())} vs {form} {pct(b.follow_up.mean())}: {100*t['diff']:+.1f} [{100*t['lo']:+.1f}, {100*t['hi']:+.1f}] p={t['p']:.3f} n={t['n']} ({t.get('method','')})")

head("E. Plain correctness (PROVISIONAL until audit part 2): no signal vs false end signals, more rows exist")
for m in M:
    c, n = cells[m]["conflicts"], cells[m]["need"]
    fe = c[c.conflict.isin(list(FALSE_END))]
    none = n[n.signal_form == "none"]
    print(m, "correct: none", pct(none.correct.mean()), "| false ends", pct(fe.correct.mean()),
          "| retrieval-supported: none", pct(none.justified_correct.mean()), "| false ends", pct(fe.justified_correct.mean()))

head("F. Retrieval-supported correctness by form, more rows exist (PROVISIONAL), and rows needed when paging")
for m in M:
    n = cells[m]["need"]
    print(m, "correct / retrieval-supported by form:", ", ".join(
        f"{f} {pct(g.correct.mean())}/{pct(g.justified_correct.mean())}" for f, g in n.groupby("signal_form")))
    more = cells[m]["core"]
    more = more[(more.task_need == "needs_all") & more.extent.isin(["more_full", "more_short"])]
    for f in ["has_more", "total_count"]:
        g = more[(more.signal_form == f) & (more.follow_up == 1)]
        print(f"   {f}, both extents with more rows: paged in {len(g)}; every needed row in {int(g.evidence_seen.sum())} of {len(g)}"
              f"; completion==1 in {pct((g.completion == 1).mean()) if len(g) else '--'}")
        g = n[(n.signal_form == f) & (n.follow_up == 1)]
        print(f"   {f}: paged in {len(g)}; ended with every row its answer needed in {int(g.evidence_seen.sum())} of {len(g)}"
              f"; completion==1 in {pct((g.completion == 1).mean()) if len(g) else '--'}")
    ex = cells[m]["core"]
    ex = ex[(ex.task_type == "exists") & (ex.task_need == "needs_all")]
    print(f"   exists task (core, needs-all, all forms and extents, n={len(ex)}): correct {pct(ex.correct.mean())}, retrieval-supported {pct(ex.justified_correct.mean())}")
    for name, sub in [("more rows exist (both extents)", ex[ex.extent.isin(["more_full", "more_short"])]),
                      ("full page, more rows", ex[ex.extent == "more_full"]),
                      ("all needs-all exists in analysis sample", analysis_sample(s[s.model == m]).query("task_type == 'exists' and arm == 'core'"))]:
        print(f"   exists, {name} (n={len(sub)}): correct {pct(sub.correct.mean())}, retrieval-supported {pct(sub.justified_correct.mean())}")

head("G. Retest disagreements on fetching, by condition")
for m in M:
    g = s[s.model == m]
    rt = g[g.arm == "retest"]
    first = g[g.arm != "retest"]
    key = ["signal_form", "extent", "task_type", "item", "conflict", "answer_format", "documented", "task_need"]
    j = rt.merge(first, on=["model", "seed", "signal_form", "extent", "task_type", "item", "replicate", "task_need"],
                 suffixes=("_r", "_f")) if False else None
    # retests share the episode's condition fields; match on every condition column except arm and episode_id
    cond = [c for c in ["signal_form", "extent", "task_need", "task_type", "item", "placement", "conflict", "documented",
                        "limit_stated", "phrasing", "answer_format", "page_limit", "doc_wording"] if c in g]
    f2 = first.copy(); r2 = rt.copy()
    for d in (f2, r2):
        d["k"] = d[cond].apply(lambda r: "|".join(map(str, r.tolist())), axis=1)
    j = r2.merge(f2[["k", "follow_up"]], on="k", suffixes=("_r", "_f"))
    dis = j[j.follow_up_r != j.follow_up_f]
    print(m, f"pairs {len(j)}, fetch disagreements {len(dis)}:",
          ", ".join(f"{a}/{b}: {n}" for (a, b), n in dis.groupby(["signal_form", "extent"]).size().sort_values(ascending=False).items()),
          "| by conflict:", dis.conflict.fillna("-").value_counts().to_dict(), "| by task:", dis.task_type.value_counts().to_dict())

head("H. Cost in tool calls (n_calls), core final-line needs-all")
for m in M:
    n, last = cells[m]["need"], cells[m]["last"]
    sig = n[n.signal_form != "none"]
    print(m, f"more rows exist: no signal {n[n.signal_form=='none'].n_calls.mean():.2f}, any main form {sig.n_calls.mean():.2f} "
          f"(+{sig.n_calls.mean() - n[n.signal_form=='none'].n_calls.mean():.2f}), has_more {n[n.signal_form=='has_more'].n_calls.mean():.2f}",
          "| full last page, saved vs no signal:", ", ".join(f"{f} {last[last.signal_form=='none'].n_calls.mean() - g.n_calls.mean():+.2f}"
                                                           for f, g in last.groupby("signal_form") if f != "none"),
          "| cap hits (all arms):", int(s[s.model == m].hit_cap.sum()))

head("I. Stated completeness when the answer was incomplete (completeness format, needs-all, retests left out; descriptive)")
for m in M:
    g = s[(s.model == m) & (s.arm != "retest") & (s.answer_format == "completeness") & (s.task_need == "needs_all")]
    for name, sub in [("all completeness-format", g), ("trigger cells (no conflict)", g[g.conflict.isna()]),
                      ("false-end cells", g[g.conflict.notna()])]:
        inc, com = sub[sub.evidence_seen == 0], sub[sub.evidence_seen == 1]
        vc = inc.stated_completeness.fillna("none").value_counts()
        vc2 = com.stated_completeness.fillna("none").value_counts()
        print(f"{m} | {name}: incomplete {len(inc)} -> " + ", ".join(f"{k} {v} ({pct(v/len(inc)) if len(inc) else '--'})" for k, v in vc.items())
              + f" || complete {len(com)} -> " + ", ".join(f"{k} {v}" for k, v in vc2.items()))

head("J. Multiplicity: significant within part vs after Holm across all main contrasts")
mu = pd.read_csv(R / "tables" / "main_multiplicity.csv")
for m in M:
    g = mu[mu.model == m]
    lost = g[g.within_part & ~g.holm_all]
    print(m, f"contrasts {len(g)}, significant within part {int(g.within_part.sum())}, kept after Holm across all {int((g.within_part & g.holm_all).sum())}; lost:",
          "; ".join(f"{r.hypothesis} {r.part} {r.test[:50]}" for r in lost.itertuples()))

head("K. Amended H4: incomplete answers by task (post hoc file)")
print(pd.read_csv(R / "tables" / "posthoc_h4_incomplete_by_task.csv").to_string(index=False))
