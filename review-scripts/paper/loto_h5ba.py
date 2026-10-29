"""Amended H5b(a) without each task in turn (flag-based, so PROVISIONAL until the disclosure labels), frozen code."""
import sys
import pandas as pd
from fplp.analysis.hypotheses import run
s = pd.read_csv(sys.argv[1], low_memory=False)
conf = ["gpt-oss-120b", "mistral-medium-3-5", "claude-sonnet-5-5"]
tasks = ["count_high_priority", "count_out_of_stock", "exists", "export_all", "filtered_count", "oldest_date"]
for t in [None, *tasks]:
    d, _ = run(s, 2000, 0, conf, None, exclude_tasks=[t] if t else None, families=("amended",))
    r = d[(d.hypothesis == "H5b") & (d.part == "a")]
    print(f"without {t or '(none: primary)'}: " + "; ".join(
        f"{x.model}: {100*x['diff']:+.1f} [{100*x.lo:+.1f}, {100*x.hi:+.1f}] p={x.p:.3f} sup={x.supported} est={x.estimable}" for _, x in r.iterrows()), flush=True)
