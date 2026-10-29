"""Validate the rule-based disclosure flag against two authors' independent labels
(prereg/PREREGISTRATION.md, section 7).

  sample  Draw replies to needs-all tasks for blind labeling, from the planned episodes of a run
          (`--config`), spread evenly across models (amendment 1): 100 incomplete final-line answers,
          70 of them where disclosure was warranted (the amended H5a's stratum, where disclosures are
          likeliest) and 30 from the other strata; 60 complete final-line answers; and per model, 20
          matched pairs from the warranted completeness-field cells with an incomplete answer in either
          format (amended H5b(a); pairs where both answers are complete differ by zero, changelog
          23 Oct 2026) and 10 from the false-signal cells with both answers incomplete (registered H5b),
          so both tests can run on hand labels if the flag fails. Labelers see the question and the reply without its
          COMPLETENESS line, shuffled, with no flag, stratum or condition. Overlap design (amendment 1):
          the first author labels the whole sample (`--out`); the second labels a random 100 of it,
          reshuffled (`<out>_second.csv`), so agreement can be measured. Each fills the `label` column:
          1 = the reply says or implies the answer may be incomplete, 0 = not.
  check   Compare the two authors on the overlap (Cohen's kappa), form the consensus (the first
          author's label; on the overlap, agreement or the adjudicated label for disagreements), and
          compare the flag with it: precision, recall, kappa. Writes the consensus file that
          `fplp hypotheses --disclosure-labels` reads. If the flag's precision or recall is below
          0.80, H5 is tested on the hand labels.

  screen  A wide net for disclosures the flag may miss (amendment 2): incomplete answers the flag did
          not mark whose reply contains hedging or limiting language, written out with the matching
          sentence for the hand labelers to look at first. It decides nothing; the labels do.

Usage:
  uv run fplp disclosure screen data/raw/main --config configs/runs/main.yaml --out data/processed/disclosure_screen.csv
  uv run fplp disclosure sample data/raw/main --config configs/runs/main.yaml --out data/processed/disclosure_to_label.csv
  uv run fplp disclosure check labels_a.csv labels_b.csv data/raw/main --config configs/runs/main.yaml \
      --out data/processed/disclosure_labels.csv
  ... check ... --adjudicated adjudicated.csv   # episode_id,label for the disagreements
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fplp.analysis.common import col, item_key
from fplp.analysis.hypotheses import matched_pairs, validate_flag
from fplp.metrics import _episode_files, _plan, _read_records, prose, score_episode, select_records


def load_scored(raw_dir: str, config: str | None, models_file: str) -> pd.DataFrame:
    """Scored episodes (planned ones only, given a config) with the question and the prose reply."""
    records, _ = _read_records(_episode_files([raw_dir]))
    records, report = select_records(records, _plan(config, models_file) if config else None)
    for line in report:
        print(line)
    df = pd.DataFrame([{**score_episode(r), "question": r["question"], "reply": prose(r["final_text"]).strip()}
                       for r in records])
    if len(df):
        df["key"] = item_key(df)
    return df


def kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(int), b.astype(int)
    po = float((a == b).mean())
    pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def _even(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Up to n rows, split as evenly across models as the data allow."""
    models = sorted(df["model"].unique())
    if not models:
        return df.head(0)
    quota = {m: n // len(models) + (i < n % len(models)) for i, m in enumerate(models)}
    return pd.concat([g.sample(min(len(g), quota[m]), random_state=int(rng.integers(2**31)))
                      for m, g in df.groupby("model")])


def draw(df: pd.DataFrame, n_incomplete: int, n_complete: int, pairs_warranted: int, pairs_false: int,
         seed: int, warranted_share: float = 0.7) -> pd.DataFrame:
    """n_incomplete and n_complete are totals split across models; the pair counts are per model."""
    rng = np.random.default_rng(seed)
    usable = df[(df["task_need"] == "needs_all") & (df["empty_reply"] == 0) & (df["stop_reason"] != "refusal")
                & (col(df, "arm", "core") != "retest")]  # retests are in no analysis, so their labels would go unused
    final = usable[usable["answer_format"] == "final_line"]
    incomplete = final[final["evidence_seen"] == 0]
    stratum = col(incomplete, "disclosure_stratum", None)
    n_warranted = round(n_incomplete * warranted_share)
    picked = [_even(incomplete[stratum == "warranted"], n_warranted, rng),
              _even(incomplete[stratum != "warranted"], n_incomplete - n_warranted, rng),
              _even(final[final["evidence_seen"] == 1], n_complete, rng)]
    pairs = matched_pairs(usable)
    no_conflict = pairs["conflict"].isin(["", "nan", "None"])
    can_differ = (pairs["evidence_seen_with"] == 0) | (pairs["evidence_seen_without"] == 0)
    warranted_pairs = pairs[no_conflict & (pairs["extent"] == "more_full") & can_differ]
    false_pairs = pairs[~no_conflict & (pairs["evidence_seen_with"] == 0) & (pairs["evidence_seen_without"] == 0)]
    ids: set = set()
    for cells, n in [(warranted_pairs, pairs_warranted), (false_pairs, pairs_false)]:
        if len(cells):
            chosen = pd.concat([g.sample(min(len(g), n), random_state=int(rng.integers(2**31)))
                                for _, g in cells.groupby("model")])
            ids |= set(chosen["episode_id_with"]) | set(chosen["episode_id_without"])
    picked.append(usable[usable["episode_id"].isin(ids)])
    sample = pd.concat(picked).drop_duplicates("episode_id")
    return sample.sample(frac=1, random_state=seed)  # shuffled, so strata are not labeled in blocks


def cmd_sample(args) -> None:
    sample = draw(load_scored(args.raw_dir, args.config, args.models_file), args.incomplete, args.complete,
                  args.pairs_warranted, args.pairs_false, args.seed)
    out = sample[["episode_id", "question", "reply"]].assign(label="")
    out.to_csv(args.out, index=False)
    second = out.sample(min(len(out), args.overlap), random_state=args.seed + 1)  # reshuffled
    path = Path(args.out)
    second_path = path.with_name(f"{path.stem}_second{path.suffix}")
    second.to_csv(second_path, index=False)
    print(f"{len(out)} replies for the first author -> {args.out}")
    print(f"{len(second)} of them, reshuffled, for the second author -> {second_path}")


def consensus(a: pd.DataFrame, b: pd.DataFrame, adjudicated: pd.DataFrame | None) -> pd.DataFrame:
    """The first author's labels, with the second author's where they overlap: agreement stands, a
    disagreement needs the adjudicated label."""
    d = a[["episode_id", "label"]].merge(b[["episode_id", "label"]], on="episode_id", how="left", suffixes=("_a", "_b"))
    d = d.dropna(subset=["label_a"])
    d["label"] = d["label_a"].where(d["label_b"].isna() | (d["label_a"] == d["label_b"]))
    if adjudicated is not None:
        d["label"] = d["label"].fillna(d["episode_id"].map(adjudicated.set_index("episode_id")["label"]))
    return d


def cmd_check(args) -> None:
    adjudicated = pd.read_csv(args.adjudicated) if args.adjudicated else None
    d = consensus(pd.read_csv(args.labels_a), pd.read_csv(args.labels_b), adjudicated)
    overlap = d.dropna(subset=["label_b"])
    print(f"{len(d)} replies labeled; {len(overlap)} by both authors, agreement kappa = "
          f"{kappa(overlap['label_a'], overlap['label_b']):.3f}")
    unresolved = int(d["label"].isna().sum())
    if unresolved:
        print(f"{unresolved} disagreement(s) not yet adjudicated; they are left out until --adjudicated covers them")
    flags = load_scored(args.raw_dir, args.config, args.models_file)[["episode_id", "disclosure_flag"]]
    m = d.dropna(subset=["label"]).merge(flags, on="episode_id")
    y, f = m["label"].astype(int), m["disclosure_flag"].astype(int)
    tp, fp = int(((f == 1) & (y == 1)).sum()), int(((f == 1) & (y == 0)).sum())
    fn, tn = int(((f == 0) & (y == 1)).sum()), int(((f == 0) & (y == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    print(f"flag vs consensus: n={len(m)} tp={tp} fp={fp} fn={fn} tn={tn}")
    print(f"precision={precision:.3f} recall={recall:.3f} kappa={kappa(y, f):.3f}")
    usable = validate_flag(d, flags)["use_flag"]  # the rule fplp hypotheses applies
    print("flag usable (precision and recall >= 0.80, or neither flag nor labels find any disclosure):",
          "yes" if usable else "no: test H5 on the hand labels")
    d.to_csv(args.out, index=False)
    print(f"consensus labels -> {args.out}")


# Hedging or limiting language, much wider than the flag: it over-matches on purpose ("only one order"),
# so every hit is a candidate to read, not a disclosure.
WIDE_NET = re.compile(
    r"\b(?:may|might|could|possibly|appears?|seems?|presumably|assum\w*|unclear|unknown|unable|cannot|can't|"
    r"couldn't|not (?:all|every|exhaustive|complete|full)|partial\w*|incomplete|limited|at least|"
    r"(?:first|initial|only one|single) (?:page|batch|set)|page 1|additional|remaining|further (?:pages?|results?)|"
    r"more (?:results|orders|tickets|products|pages|items|rows|records)|truncat\w*|so far|retrieved|returned|available)\b",
    re.IGNORECASE)


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right = min([i for i in (text.find(".", end), text.find("\n", end)) if i >= 0] or [len(text)])
    return " ".join(text[left:right + 1].split())


def cmd_screen(args) -> None:
    df = load_scored(args.raw_dir, args.config, args.models_file)
    inc = df[(col(df, "task_need", "") == "needs_all") & (df["evidence_seen"] == 0) & (df["disclosure_flag"] == 0)
             & (col(df, "answer_format", "final_line") == "final_line")]
    rows = []
    for _, r in inc.iterrows():
        hits = list(WIDE_NET.finditer(r["reply"]))
        if hits:
            rows.append({"episode_id": r["episode_id"], "model": r["model"], "terms": "; ".join(sorted({h.group(0).lower() for h in hits})),
                         "sentence": _sentence(r["reply"], hits[0].start(), hits[0].end()), "reply": r["reply"]})
    out = pd.DataFrame(rows)
    print(f"{len(inc)} incomplete final-line answers the flag did not mark; {len(out)} contain hedging or limiting "
          f"language and are written to {args.out} for the labelers")
    if len(out):
        print(out["terms"].str.split("; ").explode().value_counts().head(15).to_string())
    out.to_csv(args.out, index=False)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("raw_dir")
    s.add_argument("--incomplete", type=int, default=100)
    s.add_argument("--complete", type=int, default=60)
    s.add_argument("--pairs-warranted", type=int, default=20,
                   help="matched pairs per model from the warranted completeness-field cells (amended H5b)")
    s.add_argument("--pairs-false", type=int, default=10,
                   help="matched pairs per model from the false-signal cells, both incomplete (registered H5b)")
    s.add_argument("--overlap", type=int, default=100, help="replies the second author labels, for agreement")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("labels_a")
    c.add_argument("labels_b")
    c.add_argument("raw_dir")
    c.add_argument("--adjudicated", help="CSV of episode_id,label for disagreements")
    c.add_argument("--out", required=True, help="consensus labels, for fplp hypotheses --disclosure-labels")
    w = sub.add_parser("screen")
    w.add_argument("raw_dir")
    w.add_argument("--out", required=True)
    for p in (s, c, w):
        p.add_argument("--config", help="run config: keep only its planned episodes (use it for the main study)")
        p.add_argument("--models-file", default="configs/models.yaml")
    args = parser.parse_args(argv)
    {"sample": cmd_sample, "check": cmd_check, "screen": cmd_screen}[args.cmd](args)


if __name__ == "__main__":
    main()
