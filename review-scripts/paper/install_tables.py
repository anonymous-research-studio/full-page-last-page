"""Copy the frozen `fplp tables` output into the manuscript (what `make paper` does), with one change:
the three H5 verdict rows read "pending" until the disclosure labels are in (lead author's instruction,
25 Oct 2026). The flag-based H5 verdicts stay in tex/verdict_rows.tex for the record.

  python install_tables.py <tex dir> <manuscript current/ dir>
"""
import re
import shutil
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
H5 = ("H5a", "H5b", "H5 (reg.)")
for f in sorted(src.glob("*_rows.tex")):
    text = f.read_text()
    if f.name == "verdict_rows.tex":
        lines = []
        for line in text.splitlines():
            label = line.split(" & ")[0]
            if label in H5:
                n = line.count(" & ")
                line = label + " & pending" * (n - 1) + r" & \textbf{pending} \\"
                print("pending:", line)
            lines.append(line)
        text = "\n".join(lines) + "\n"
    (dst / "tables" / f.name).write_text(text)
    print("installed", f.name)
shutil.copy2(src / "calibration.pdf", dst / "figures" / "calibration.pdf")
print("installed calibration.pdf")
