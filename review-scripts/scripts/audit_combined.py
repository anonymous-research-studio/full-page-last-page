"""Combine the audit parts into one blinded worksheet: every reply in a seeded random order, with new ids.

Reads each part's drawn sample (in part order) and the raw logs, builds each reply's blinded view as
`scripts/audit_worksheet.py --blinded` does, shuffles all replies with a seeded generator, and numbers
them 1..N. Writes, beside <out>:
  <out>_blinded.html, <out>_blinded.csv   the combined blinded worksheet (new ids only);
  audit_key_combined.csv                  new audit id -> part, the part's audit id, episode, model, stratum,
                                          weight and condition;
  audit_verdicts_combined.csv             audit_id (new), verdict, note; never overwritten.
An existing key that would change stops the script, so verdicts already entered keep their meaning.
Score it with `scripts/audit_error_rate.py --part audit_key_combined.csv audit_verdicts_combined.csv`
(the key carries model, stratum and weight). Use either the combined files or the part files, not both:
the error-rate script stops if an episode appears twice.

  uv run python scripts/audit_combined.py REVIEW/final/audit_sample_part1_gpt-oss_claude.csv \
      REVIEW/final/audit_sample_part2_mistral.csv --raw data/raw/main --out REVIEW/final/audit_worksheet_combined
"""

from __future__ import annotations

import argparse
import io
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from audit_worksheet import KEY_COLUMNS, blinded, build, extras, records_by_id, to_html_blinded


def combine(samples: list[pd.DataFrame], by_id: dict[str, dict], seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    views, keys = [], []
    for part, sample in enumerate(samples, start=1):
        table = build(sample, by_id)
        more = {int(a): extras(by_id[e]) for a, e in zip(sample["audit_id"], sample["episode_id"], strict=True)}
        view = blinded(table, more).rename(columns={"audit_id": "part_audit_id"})
        key = table[KEY_COLUMNS].rename(columns={"audit_id": "part_audit_id"}).assign(part=part)
        views.append(view.assign(part=part))
        keys.append(key)
    view, key = pd.concat(views, ignore_index=True), pd.concat(keys, ignore_index=True)
    order = list(range(len(view)))
    random.Random(f"{seed}:combined").shuffle(order)
    view = view.iloc[order].reset_index(drop=True)
    view.insert(0, "audit_id", range(1, len(view) + 1))
    key = view[["audit_id", "part", "part_audit_id"]].merge(key, on=["part", "part_audit_id"], validate="one_to_one")
    key = key[["audit_id", "part", "part_audit_id", *[c for c in KEY_COLUMNS if c != "audit_id"]]]
    return view.drop(columns=["part", "part_audit_id"]), key


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("samples", nargs="+", help="each part's drawn sample CSV, in part order")
    p.add_argument("--raw", nargs="+", required=True, help="raw episode logs (files or directories)")
    p.add_argument("--out", required=True, help="path without extension, e.g. REVIEW/final/audit_worksheet_combined")
    p.add_argument("--seed", type=int, default=20261025)
    args = p.parse_args(argv)
    view, key = combine([pd.read_csv(s) for s in args.samples], records_by_id(args.raw), args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    key_path, verdicts = out.with_name("audit_key_combined.csv"), out.with_name("audit_verdicts_combined.csv")
    if key_path.exists() and not pd.read_csv(key_path).equals(pd.read_csv(io.StringIO(key.to_csv(index=False)))):
        raise SystemExit(f"{key_path} exists and would change; verdicts keyed to it would lose their meaning. Nothing written.")
    base = out.with_name(out.name + "_blinded")
    view.to_csv(base.with_suffix(".csv"), index=False)
    key.to_csv(key_path, index=False)
    source = (f"{len(view)} replies from {len(args.samples)} parts, in a seeded random order with new ids. Part, original "
              f"audit id, model, condition, stratum, weight and episode id are in {key_path.name}, not here.")
    base.with_suffix(".html").write_text(to_html_blinded(view, "Correctness audit worksheet, combined (blinded)", source,
                                                         verdicts.name))
    if verdicts.exists():  # never overwrite verdicts already entered
        print(f"kept the existing {verdicts}")
    else:
        pd.DataFrame({"audit_id": range(1, len(view) + 1), "verdict": "", "note": ""}).to_csv(verdicts, index=False)
    print(f"wrote {len(view)} replies -> {base.with_suffix('.html')}, {base.with_suffix('.csv')}, {key_path} and {verdicts}")


if __name__ == "__main__":
    main()
