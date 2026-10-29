"""Blinded labeling worksheets for the disclosure-flag validation: the registered sample plus the supplement that
lets the flag's precision and recall be estimated (changelog, 25 Oct 2026; the supplement is descriptive only).

The registered sample is `fplp disclosure sample`'s draw, unchanged (`--registered`, `--registered-second`).
The supplement adds, from the main study's needs-all replies outside the registered sample (retests left out,
as the registered sampler does):
  F  every reply the flag marks (census): precision;
  W  every incomplete final-line reply the flag missed that the registered wide-net screen (`fplp disclosure
     screen`, amendment 2) caught (census): the likeliest missed disclosures;
  U  a seeded random sample of the other incomplete final-line replies the flag missed;
  C  a seeded random sample of the incomplete completeness-format replies the flag missed (their prose,
     without the COMPLETENESS line, is what H5b's prose part reads).
Each supplement reply carries its sampling weight (population / sampled; 1 for a census), so missed disclosures
can be estimated over the whole population. Labelers see only a worksheet id, the question and the reply
without its COMPLETENESS line, shuffled; the key (`key.csv`) holds everything else and is not for labelers.
Labeler A gets every reply; labeler B gets the registered overlap of 100 plus a stratified overlap of the
supplement, reshuffled with new ids. Label files are never overwritten. `scripts/disclosure_labels.py` reads
the returned labels.

  uv run python scripts/disclosure_worksheet.py --scored data/processed/main.csv --raw data/raw/main \
      --registered data/processed/disclosure_to_label.csv --registered-second data/processed/disclosure_to_label_second.csv \
      --screen data/processed/disclosure_screen.csv --out-dir REVIEW/disclosure
"""

from __future__ import annotations

import argparse
import html
import json
import random
from pathlib import Path

import pandas as pd

from fplp.metrics import _episode_files, _read_records, prose

CONDITION = ["arm", "signal_form", "conflict", "extent", "task_type", "answer_format", "documented"]


def population(scored: pd.DataFrame) -> pd.DataFrame:
    """Needs-all replies the registered sampler draws from: no empty reply, no refusal, no retest."""
    keep = (scored["task_need"] == "needs_all") & (scored["empty_reply"] == 0) & (scored["arm"] != "retest")
    if "stop_reason" in scored:
        keep &= scored["stop_reason"] != "refusal"
    return scored[keep]


def supplement(scored: pd.DataFrame, registered: set[str], screen: set[str], n_u: int, n_c: int, seed: int) -> pd.DataFrame:
    pop = population(scored)
    out = pop[~pop["episode_id"].isin(registered)]
    missed = (out["evidence_seen"] == 0) & (out["disclosure_flag"] == 0)
    strata = {
        "F": out[out["disclosure_flag"] == 1],
        "W": out[missed & (out["answer_format"] == "final_line") & out["episode_id"].isin(screen)],
        "U": out[missed & (out["answer_format"] == "final_line") & ~out["episode_id"].isin(screen)],
        "C": out[missed & (out["answer_format"] == "completeness")],
    }
    rng = random.Random(f"{seed}:disclosure-supplement")
    parts = []
    for name, frame in strata.items():
        ids = sorted(frame["episode_id"])
        n = {"U": n_u, "C": n_c}.get(name, len(ids))
        drawn = ids if n >= len(ids) else rng.sample(ids, n)
        parts.append(frame[frame["episode_id"].isin(drawn)].assign(part=name, population=len(ids), sampled=len(drawn),
                                                                     weight=len(ids) / max(len(drawn), 1)))
    return pd.concat(parts, ignore_index=True)


STYLE = ("body{font:15px/1.5 -apple-system,sans-serif;max-width:900px;margin:0 auto;padding:24px 16px}"
         "section{border:1px solid #ccc;border-radius:8px;padding:12px 14px;margin:14px 0}"
         "pre{white-space:pre-wrap;word-break:break-word;font:13px/1.45 ui-monospace,Menlo,monospace;background:#f6f6f8;"
         "padding:10px;border-radius:6px}"
         "@media (prefers-color-scheme:dark){body{background:#161618;color:#ececf0}pre{background:#222}section{border-color:#444}}")


def worksheet_html(view: pd.DataFrame, title: str) -> str:
    e = html.escape
    parts = [(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
              f"content='width=device-width, initial-scale=1'><title>{e(title)}</title><style>{STYLE}</style></head><body>"),
             (f"<h1>{e(title)}</h1><p>Label each reply in the labels file (worksheet id, label, note): <b>1</b> if the reply "
              "says or implies the answer may be incomplete, <b>0</b> if not. See the instructions file.</p>")]
    for _, r in view.iterrows():
        parts.append(f"<section id='{e(r['wid'])}'><h2>{e(r['wid'])}</h2><p><b>Question:</b> {e(r['question'])}</p>"
                     f"<pre>{e(r['reply'])}</pre></section>")
    parts.append("</body></html>")
    return "\n".join(parts)


def write_blank(path: Path, wids: list[str]) -> str:
    if path.exists():  # never overwrite labels already entered
        return f"kept the existing {path}"
    pd.DataFrame({"wid": wids, "label": "", "note": ""}).to_csv(path, index=False)
    return f"wrote {path}"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scored", required=True)
    p.add_argument("--raw", nargs="+", required=True)
    p.add_argument("--registered", required=True)
    p.add_argument("--registered-second", required=True)
    p.add_argument("--screen", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--n-random-final", type=int, default=120)
    p.add_argument("--n-random-completeness", type=int, default=60)
    p.add_argument("--second-supplement", default="F:10,W:25,U:15", help="labeler B's overlap of the supplement, per part")
    p.add_argument("--seed", type=int, default=20261025)
    args = p.parse_args(argv)
    scored = pd.read_csv(args.scored)
    reg, reg2 = pd.read_csv(args.registered), pd.read_csv(args.registered_second)
    screen = set(pd.read_csv(args.screen)["episode_id"])
    sup = supplement(scored, set(reg["episode_id"]), screen, args.n_random_final, args.n_random_completeness, args.seed)
    records, _ = _read_records(_episode_files(args.raw))
    text = {r["episode_id"]: (r["question"], prose(r["final_text"]).strip()) for r in records}
    reg_part = scored[scored["episode_id"].isin(reg["episode_id"])].assign(part="R", population=pd.NA, sampled=pd.NA, weight=pd.NA)
    allrows = pd.concat([reg_part, sup], ignore_index=True)
    allrows[["question", "reply"]] = [text[e] for e in allrows["episode_id"]]
    # Labeler A: every reply, shuffled, new ids.
    order = list(allrows.index)
    random.Random(f"{args.seed}:labeler-A").shuffle(order)
    a = allrows.loc[order].reset_index(drop=True)
    a["wid"] = [f"A{i:03d}" for i in range(1, len(a) + 1)]
    # Labeler B: the registered overlap plus a stratified overlap of the supplement, reshuffled, new ids.
    rng = random.Random(f"{args.seed}:labeler-B")
    quota = {k: int(v) for k, v in (x.split(":") for x in args.second_supplement.split(","))}
    pick = list(reg2["episode_id"])
    for part, n in quota.items():
        ids = sorted(sup.loc[sup["part"] == part, "episode_id"])
        pick += ids if n >= len(ids) else rng.sample(ids, n)
    rng.shuffle(pick)
    b = a.set_index("episode_id").loc[pick].reset_index()
    b["wid_B"] = [f"B{i:03d}" for i in range(1, len(b) + 1)]
    a = a.merge(b[["episode_id", "wid_B"]], on="episode_id", how="left")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key_cols = ["wid", "wid_B", "episode_id", "part", "population", "sampled", "weight", "model", *CONDITION, "evidence_seen",
                "disclosure_flag", "disclosure_stratum", "stated_completeness"]
    a[key_cols].to_csv(out / "key.csv", index=False)
    for who, view, wcol in (("A", a, "wid"), ("B", b, "wid_B")):
        # Each labeler's folder holds only what that labeler may see; the key and inputs stay outside it.
        folder = out / f"for-labeler-{who}"
        folder.mkdir(exist_ok=True)
        v = view[[wcol, "question", "reply"]].rename(columns={wcol: "wid"})
        v.to_csv(folder / "worksheet.csv", index=False)
        (folder / "worksheet.html").write_text(worksheet_html(v, f"Disclosure labels, labeler {who} ({len(v)} replies)"))
        print(write_blank(folder / "labels.csv", list(v["wid"])))
    counts = a.groupby("part").agg(replies=("episode_id", "size"), population=("population", "first"), in_B=("wid_B", "count"))
    print(counts.to_string())
    print(f"labeler A: {len(a)} replies; labeler B: {len(b)} replies -> {out}")
    (out / "manifest.json").write_text(json.dumps({"seed": args.seed, "n_random_final": args.n_random_final,
                                                   "n_random_completeness": args.n_random_completeness,
                                                   "second_supplement": quota, "labeler_A": len(a), "labeler_B": len(b),
                                                   "parts": counts.reset_index().astype(str).to_dict(orient="records")}, indent=1))


if __name__ == "__main__":
    main()
