"""Hand labels for the disclosure-flag validation, back from the two labelers (changelog, 25 Oct 2026).

  convert   Check each returned labels file against its worksheet, then turn worksheet ids into episode ids.
            The registered sample goes out in the format `fplp disclosure check` reads (`labels_a.csv`,
            `labels_b.csv`: episode_id,label), the supplement with its parts and weights
            (`supplement_labels.csv`), and every disagreement on the overlap, registered or not, in
            `to_adjudicate.csv` (no flag, part or condition in it). Nothing is written if any check fails.
  estimate  The supplement's weighted estimates. They are descriptive: the registered sample, through
            `fplp disclosure check`, decides the 0.80 rule. The flag's precision is read on every flagged reply
            (a census); its recall over incomplete answers counts missed disclosures in the census parts once
            and scales those in the random parts by their weights (population / sampled), with a bootstrap
            within the random parts; agreement is Cohen's kappa on the overlap.

Supplement labels never go to `fplp disclosure check` or `fplp hypotheses`: those count every labeled reply
unweighted, and the hand-label fallback would test H5 on an enriched sample.

Usage:
  uv run python scripts/disclosure_labels.py convert --dir REVIEW/disclosure --labels-a returned/A.csv \
      --labels-b returned/B.csv --out-dir REVIEW/disclosure/returned [--adjudicated adjudicated.csv]
  uv run fplp disclosure check REVIEW/disclosure/returned/labels_a.csv REVIEW/disclosure/returned/labels_b.csv \
      data/raw/main --config configs/runs/main.yaml --out data/processed/disclosure_labels.csv \
      [--adjudicated adjudicated.csv]
  uv run python scripts/disclosure_labels.py estimate --dir REVIEW/disclosure --returned REVIEW/disclosure/returned \
      --consensus data/processed/disclosure_labels.csv --out REVIEW/disclosure/returned/supplement_estimates.csv

`adjudicated.csv` has columns episode_id,label, one row per disagreement listed in `to_adjudicate.csv`; the same
file serves both commands.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from fplp.analysis.disclosure import kappa

LABELS = {"0": 0, "1": 1, "0.0": 0, "1.0": 1}  # a spreadsheet may write 1 as 1.0


def read_labels(path: str | Path, ids: list[str], other_ids: list[str] | None = None,
                ) -> tuple[pd.DataFrame, list[str], list[str]]:
    """A returned labels file matched to its worksheet ids: columns by name, every id exactly once, every label 0
    or 1. Returns the labels (wid, label, note), the problems (empty when the file can be used) and warnings."""
    raw, warnings = Path(path).read_bytes(), []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("mac_roman")
        warnings.append(f"{path}: not UTF-8, read as Mac Roman; ids and labels are ASCII, so only notes can be affected")
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in ("wid", "label") if c not in df.columns]
    if missing:
        return df, [f"{path}: no column named {', '.join(missing)} (columns: {', '.join(df.columns)})"], warnings
    if "note" not in df.columns:
        df["note"] = ""
    df = df.assign(wid=df["wid"].str.strip(), label=df["label"].str.strip())
    df = df[(df["wid"] != "") | (df["label"] != "")]  # trailing blank rows a spreadsheet adds
    problems, known = [], set(ids)
    if other_ids and set(df["wid"]) <= set(other_ids) and not set(df["wid"]) & known:
        return df, [f"{path}: every id belongs to the other labeler's worksheet; the files may be swapped"], warnings
    for what, bad in [("duplicated", sorted(set(df.loc[df["wid"].duplicated(), "wid"]))),
                      ("not in the worksheet", sorted(set(df["wid"]) - known)),
                      ("missing", sorted(known - set(df["wid"]))),
                      ("with no label", sorted(df.loc[df["label"] == "", "wid"])),
                      ("with a label other than 0 or 1",
                       [f"{w}={v!r}" for w, v in zip(df["wid"], df["label"], strict=True) if v and v not in LABELS])]:
        if bad:
            problems.append(f"{path}: {len(bad)} id(s) {what}: {', '.join(bad[:12])}{' ...' if len(bad) > 12 else ''}")
    if problems:
        return df, problems, warnings
    return df.assign(label=df["label"].map(LABELS))[["wid", "label", "note"]], [], warnings


def read_adjudicated(path: str | Path | None) -> pd.Series:
    if not path:
        return pd.Series(dtype=float)
    adj = pd.read_csv(path, dtype=str, keep_default_na=False)
    adj.columns = [str(c).strip().lower() for c in adj.columns]
    adj = adj.assign(episode_id=adj["episode_id"].str.strip(), label=adj["label"].str.strip())
    bad = adj[~adj["label"].isin(LABELS)]
    if len(bad) or adj["episode_id"].duplicated().any():
        sys.exit(f"{path}: every row needs a unique episode_id and a label of 0 or 1")
    return adj.set_index("episode_id")["label"].map(LABELS).astype(float)


def merge(key: pd.DataFrame, a: pd.DataFrame, b: pd.DataFrame, adjudicated: pd.Series) -> pd.DataFrame:
    """Every labeled reply with both labels and the consensus: labeler A's label, with labeler B's where they
    overlap; agreement stands, a disagreement takes the adjudicated label (missing until adjudicated)."""
    m = key.merge(a.rename(columns={"label": "label_a", "note": "note_a"}), on="wid", how="left")
    m = m.merge(b.rename(columns={"wid": "wid_B", "label": "label_b", "note": "note_b"}), on="wid_B", how="left")
    m["label"] = m["label_a"].where(m["label_b"].isna() | (m["label_a"] == m["label_b"]))
    return m.assign(label=m["label"].fillna(m["episode_id"].map(adjudicated)))


def cmd_convert(args) -> None:
    d = Path(args.dir)
    key = pd.read_csv(d / "key.csv", dtype={"wid": str, "wid_B": str, "episode_id": str})
    sheets = {who: pd.read_csv(d / f"for-labeler-{who}" / "worksheet.csv", dtype=str) for who in "AB"}
    problems = []
    if set(sheets["A"]["wid"]) != set(key["wid"]):
        problems.append("labeler A's worksheet ids differ from the key's")
    if set(sheets["B"]["wid"]) != set(key["wid_B"].dropna()):
        problems.append("labeler B's worksheet ids differ from the key's")
    inputs = d / "inputs"
    if (inputs / "disclosure_to_label.csv").exists():  # the registered draw, as `fplp disclosure sample` wrote it
        reg = set(pd.read_csv(inputs / "disclosure_to_label.csv", dtype=str)["episode_id"])
        reg2 = set(pd.read_csv(inputs / "disclosure_to_label_second.csv", dtype=str)["episode_id"])
        r = key[key["part"] == "R"]
        if set(r["episode_id"]) != reg or set(r.loc[r["wid_B"].notna(), "episode_id"]) != reg2:
            problems.append("the key's registered part differs from the registered draw in inputs/")
    a, pa, wa = read_labels(args.labels_a, list(sheets["A"]["wid"]), list(sheets["B"]["wid"]))
    b, pb, wb = read_labels(args.labels_b, list(sheets["B"]["wid"]), list(sheets["A"]["wid"]))
    for line in wa + wb:
        print("note:", line)
    problems += pa + pb
    if problems:
        sys.exit("Not converted; nothing written:\n  " + "\n  ".join(problems))
    adjudicated = read_adjudicated(args.adjudicated)
    m = merge(key, a, b, adjudicated)
    m[["label_a", "label_b", "label"]] = m[["label_a", "label_b", "label"]].astype("Int64")  # 1, not 1.0, in the files
    overlap = m[m["label_b"].notna()]
    split = overlap["label_a"] != overlap["label_b"]
    stray = sorted(set(adjudicated.index) - set(overlap.loc[split, "episode_id"]))
    if stray:
        sys.exit(f"{args.adjudicated}: {len(stray)} episode id(s) that are not disagreements: {', '.join(stray[:12])}")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reg = m[m["part"] == "R"]
    reg[["episode_id", "label_a"]].rename(columns={"label_a": "label"}).to_csv(out / "labels_a.csv", index=False)
    reg.loc[reg["label_b"].notna(), ["episode_id", "label_b"]].rename(columns={"label_b": "label"}).to_csv(
        out / "labels_b.csv", index=False)
    sup_cols = ["wid", "wid_B", "episode_id", "part", "population", "sampled", "weight", "model", "answer_format",
                "evidence_seen", "disclosure_flag", "label_a", "label_b", "label"]
    m.loc[m["part"] != "R", sup_cols].to_csv(out / "supplement_labels.csv", index=False)
    text = sheets["A"].set_index("wid")[["question", "reply"]]
    disagree = overlap[split].join(text, on="wid")
    disagree[["episode_id", "wid", "wid_B", "question", "reply", "label_a", "label_b", "note_a", "note_b"]].assign(
        adjudicated=disagree["episode_id"].map(adjudicated)).to_csv(out / "to_adjudicate.csv", index=False)
    print(f"labeler A: {len(a)} labels, {int(a['label'].sum())} marked 1; labeler B: {len(b)}, {int(b['label'].sum())}")
    for name, g in [("registered overlap", overlap[overlap["part"] == "R"]),
                    ("supplement overlap", overlap[overlap["part"] != "R"]), ("all overlap", overlap)]:
        print(f"{name}: {len(g)} replies, {int((g['label_a'] != g['label_b']).sum())} disagreement(s), "
              f"kappa = {kappa(g['label_a'], g['label_b']):.3f}")
    left = int(m["label"].isna().sum())
    print(f"{int(split.sum())} disagreement(s) -> {out / 'to_adjudicate.csv'}; {left} not yet adjudicated")
    print(f"registered sample: {len(reg)} replies -> {out / 'labels_a.csv'}, "
          f"{int(reg['label_b'].notna().sum())} -> {out / 'labels_b.csv'} (for `fplp disclosure check`)")
    print(f"supplement: {int((m['part'] != 'R').sum())} replies -> {out / 'supplement_labels.csv'} (for `estimate` only)")


def wilson(k: int, n: int) -> tuple[float, float]:
    return tuple(float(x) for x in proportion_confint(k, n, method="wilson")) if n else (np.nan, np.nan)


def recall_parts(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per reply, its weight if it is a disclosed incomplete answer the flag marked (true positive) or missed."""
    disclosed = ((rows["evidence_seen"] == 0) & (rows["label"] == 1)).to_numpy() * rows["w"].to_numpy()
    flag = (rows["disclosure_flag"] == 1).to_numpy()
    return disclosed * flag, disclosed * ~flag


def estimate(rows: pd.DataFrame, n_boot: int = 10_000, seed: int = 0) -> list[dict]:
    """rows: every labeled reply (registered and supplement) with part, w (1 for a census or the registered sample,
    population / sampled for a random part), evidence_seen, disclosure_flag, label (consensus) and model."""
    out = []
    flagged = rows[rows["disclosure_flag"] == 1]
    if (flagged["w"] != 1).any():
        sys.exit("a flagged reply has a weight other than 1; precision assumes every flagged reply is labeled")
    for scope, g in [("every flagged reply", flagged), ("flagged incomplete answers", flagged[flagged["evidence_seen"] == 0])]:
        k, n = int(g["label"].sum()), len(g)
        lo, hi = wilson(k, n)
        out.append({"quantity": "precision", "scope": scope, "model": "all", "value": k / n if n else np.nan,
                    "lo": lo, "hi": hi, "n": n, "interval": "Wilson 95%"})
    random_parts = [p for p, g in rows.groupby("part") if (g["w"] != 1).any()]
    rng = np.random.default_rng(seed)
    for model in ["all", *sorted(rows["model"].unique())]:
        g = rows if model == "all" else rows[rows["model"] == model]
        tp_i, fn_i = recall_parts(g)
        tp, fn = float(tp_i.sum()), float(fn_i.sum())
        # Census parts and the registered sample are fixed; each random part is resampled within itself.
        fixed = ~g["part"].isin(random_parts).to_numpy()
        btp, bfn = np.full(n_boot, tp_i[fixed].sum()), np.full(n_boot, fn_i[fixed].sum())
        for part in random_parts:
            idx = np.flatnonzero((g["part"] == part).to_numpy())
            if len(idx):
                draw = idx[rng.integers(0, len(idx), (n_boot, len(idx)))]
                btp, bfn = btp + tp_i[draw].sum(axis=1), bfn + fn_i[draw].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            boot = btp / (btp + bfn)
        defined = boot[np.isfinite(boot)]
        lo, hi = np.percentile(defined, [2.5, 97.5]) if len(defined) else (np.nan, np.nan)
        incomplete = float(g.loc[g["evidence_seen"] == 0, "w"].sum())
        n_inc = int((g["evidence_seen"] == 0).sum())
        out.append({"quantity": "recall, incomplete answers", "scope": f"true positives {tp:g}, missed (weighted) {fn:.1f}",
                    "model": model, "value": tp / (tp + fn) if tp + fn else np.nan, "lo": lo, "hi": hi, "n": n_inc,
                    "interval": f"bootstrap 95% within {', '.join(random_parts) or 'no random part'}; "
                    f"{1 - len(defined) / n_boot:.1%} of replicates undefined"})
        out.append({"quantity": "disclosures among incomplete answers (weighted)", "scope": f"of {incomplete:.0f}",
                    "model": model, "value": tp + fn, "lo": np.nan, "hi": np.nan, "n": n_inc, "interval": ""})
    return out


def cmd_estimate(args) -> None:
    key = pd.read_csv(Path(args.dir) / "key.csv", dtype={"wid": str, "wid_B": str, "episode_id": str})
    sup = pd.read_csv(Path(args.returned) / "supplement_labels.csv", dtype={"episode_id": str})
    cons = pd.read_csv(args.consensus, dtype={"episode_id": str})  # `fplp disclosure check` output
    reg = key[key["part"] == "R"].merge(cons[["episode_id", "label_a", "label_b", "label"]], on="episode_id", how="left")
    if len(cons) != len(reg) or set(cons["episode_id"]) != set(reg["episode_id"]):
        sys.exit(f"{args.consensus} does not hold exactly the registered sample's {len(reg)} replies")
    rows = pd.concat([reg.assign(w=1.0), sup.assign(w=sup["weight"].astype(float))], ignore_index=True)
    left = rows[rows["label"].isna()]
    if len(left):
        sys.exit(f"{len(left)} disagreement(s) not yet adjudicated ({', '.join(left['episode_id'][:12])}); "
                 "adjudicate them first, then rerun convert and `fplp disclosure check` with --adjudicated")
    rows["label"] = rows["label"].astype(int)
    res = pd.DataFrame(estimate(rows, args.n_boot, args.seed))
    overlap = rows[rows["label_b"].notna()]
    for name, g in [("registered", overlap[overlap["part"] == "R"]), ("supplement", overlap[overlap["part"] != "R"]),
                    ("all", overlap)]:
        res.loc[len(res)] = {"quantity": "kappa between labelers", "scope": f"{name} overlap", "model": "all",
                             "value": kappa(g["label_a"], g["label_b"]), "lo": np.nan, "hi": np.nan, "n": len(g),
                             "interval": ""}
    with pd.option_context("display.width", 200, "display.max_colwidth", 80):
        print("Supplement estimates (descriptive; the registered check decides the 0.80 rule):")
        print(res.round(3).to_string(index=False))
    if args.out:
        res.to_csv(args.out, index=False)
        print(f"-> {args.out}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--dir", required=True, help="the folder with key.csv, inputs/ and the labelers' worksheets")
    c.add_argument("--labels-a", required=True)
    c.add_argument("--labels-b", required=True)
    c.add_argument("--out-dir", required=True)
    c.add_argument("--adjudicated")
    c.set_defaults(func=cmd_convert)
    e = sub.add_parser("estimate")
    e.add_argument("--dir", required=True)
    e.add_argument("--returned", required=True, help="convert's output folder")
    e.add_argument("--consensus", required=True, help="`fplp disclosure check` output for the registered sample")
    e.add_argument("--out")
    e.add_argument("--n-boot", type=int, default=10_000)
    e.add_argument("--seed", type=int, default=0)
    e.set_defaults(func=cmd_estimate)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
