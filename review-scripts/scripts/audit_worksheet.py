"""Build the worksheet for a drawn audit sample: a reading view (HTML), the same fields as CSV, and a
verdicts-only file to fill in.

For each sampled reply: its audit id, episode id, model, stratum and condition; the question and gold
answer; the model's full final text; the scorer's reading (the final answer it parsed, `correct`, the
COMPLETENESS line where the answer format asks for one, the disclosure flag); a summary of the calls
(each call's turn, arguments and outcome, and the rows seen). Verdicts go only in the verdicts file
(`audit_id`, `verdict`, `note`, pre-filled with the part's ids). The verdict is the auditor's judgment of
the scorer's correctness reading (`scorer_correct`): "agree", "disagree" or "unsure".
`scripts/audit_error_rate.py` merges the verdicts with the worksheet by audit id and computes a
stratum-weighted parser error rate per model.

  uv run python scripts/audit_worksheet.py REVIEW/final/audit_sample_part1_gpt-oss_claude.csv data/raw/main \
      --out REVIEW/final/audit_worksheet_part1
writes <out>.html, <out>.csv and the verdicts file (audit_verdicts_part1.csv: "worksheet" in the name becomes
"verdicts"; otherwise <out>_verdicts.csv), never overwriting an existing verdicts file.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd

from fplp.metrics import _episode_files, _read_records, final_answer, normalize, score_episode

CONDITION = ["arm", "signal_form", "conflict", "extent", "task_type", "task_need", "answer_format", "documented"]
COLUMNS = ["audit_id", "episode_id", "model", "stratum", "weight", *CONDITION, "question", "gold",
           "scorer_final_answer", "scorer_correct", "stated_completeness", "disclosure_flag", "evidence_seen",
           "calls_summary", "final_text"]


def _arg_text(args: dict) -> str:
    shown = {k: (str(v)[:14] + "…" if len(str(v)) > 15 else v) for k, v in args.items() if v not in (None, "")}
    return ", ".join(f"{k}={v}" for k, v in shown.items())


def calls_summary(rec: dict) -> str:
    """One line per call (turn, tool, arguments, outcome), then the rows of the target set seen."""
    lines, seen = [], set()
    for x in rec["calls"]:
        turn = f"t{x['turn']}" if x.get("turn") is not None else "t?"
        if x["error"]:
            outcome = f"error: {x['error']}"
        elif not x["is_target"]:
            outcome = "not the target query: 0 answer rows"
        elif x["n_rows"]:
            outcome = f"rows {x['offset'] + 1}-{x['offset'] + x['n_rows']}"
            seen.update(range(x["offset"], x["offset"] + x["n_rows"]))
        else:
            outcome = "0 rows"
        lines.append(f"{turn} {x['tool']}({_arg_text(x['arguments'])}) -> {outcome}")
    lines.append(f"rows seen: {len(seen)} of {rec['n_items']}")
    return "\n".join(lines)


_ID_PATTERN = {"id_set": r"TCK-\d+", "sku_any": r"SKU-\d+"}


def scorer_ids(rec: dict) -> tuple[list[str], str] | None:
    """The ids the scorer reads for an id answer, as `fplp.metrics.is_correct` reads them: from the final
    line, or from the whole reply when the final line holds none. None for other answer types."""
    pattern = _ID_PATTERN.get(rec["gold"]["answer_type"])
    if pattern is None:
        return None
    final = set(re.findall(pattern, final_answer(rec["final_text"]).upper()))
    if final:
        return sorted(final), "from the final line"
    return sorted(set(re.findall(pattern, normalize(rec["final_text"]).upper()))), "from the body; the final line has none"


def served_rows(rec: dict, skus: list[str]) -> dict[str, str]:
    """Each named SKU's row as the server returned it (first time served), with the call that served it."""
    found: dict[str, str] = {}

    def walk(o, where: str) -> None:
        if isinstance(o, dict):
            if o.get("sku") in skus and o["sku"] not in found:
                found[o["sku"]] = f"{json.dumps(o)} ({where})"
            for v in o.values():
                walk(v, where)
        elif isinstance(o, list):
            for v in o:
                walk(v, where)

    for x in rec["calls"]:
        if x["is_target"] and not x["error"]:
            try:
                walk(json.loads(x["output"]), f"served at t{x.get('turn', '?')}, rows {x['offset'] + 1}-{x['offset'] + x['n_rows']}")
            except (json.JSONDecodeError, TypeError):
                continue
    return {s: found.get(s, "not in any served row") for s in skus}


def gold_text(rec: dict) -> str:
    """The gold as every worksheet shows it: the value, or for a name-one task, which has no single value,
    the rule `fplp.metrics.is_correct` applies, with the accepted SKUs."""
    gold = rec["gold"]
    if gold["answer_type"] == "sku_any":
        return (f"rule: any in-stock SKU among the {rec['n_items']} matching rows; correct if every SKU the answer "
                f"names is one of the {len(gold['accepted'])} accepted: {', '.join(gold['accepted'])}")
    return json.dumps(gold.get("value", gold.get("accepted")))


def extras(rec: dict) -> list[tuple[str, str]]:
    """Rows the auditor needs beyond the parsed fields: the served row of each SKU a name-one answer names,
    and, for an export whose final line has no ids, the ids the scorer took from the body."""
    taken = scorer_ids(rec)
    if taken is None:
        return []
    ids, source = taken
    gold, out = rec["gold"], []
    if gold["answer_type"] == "sku_any":
        out.append((f"SKU(s) the scorer took ({source})", ", ".join(ids) or "none"))
        for sku, row in served_rows(rec, ids).items():
            out.append((f"served row for {sku}", row))
    elif source.startswith("from the body"):
        want = set(gold["value"])
        out.append((f"IDs the scorer took ({source})", f"{len(ids)}: {', '.join(ids) or 'none'}"))
        missing, extra = ", ".join(sorted(want - set(ids))) or "none", ", ".join(sorted(set(ids) - want)) or "none"
        out.append(("against the gold IDs",
                    f"{len(set(ids) & want)} of {len(want)} gold IDs present; missing: {missing}; extra: {extra}"))
    return out


def records_by_id(raw: list[str]) -> dict[str, dict]:
    records, _ = _read_records(_episode_files(raw))
    by_id: dict[str, dict] = {}
    for r in records:
        by_id.setdefault(r["episode_id"], r)
    return by_id


def build(sample: pd.DataFrame, raw: list[str] | dict[str, dict]) -> pd.DataFrame:
    by_id = raw if isinstance(raw, dict) else records_by_id(raw)
    if missing := sorted(set(sample["episode_id"]) - set(by_id)):
        raise SystemExit(f"{len(missing)} sampled episode(s) not in the raw logs, e.g. {missing[:3]}")
    rows = []
    for _, s in sample.iterrows():
        rec = by_id[s["episode_id"]]
        scored, c = score_episode(rec), rec["condition"]
        completeness = c.get("answer_format", "final_line") == "completeness"
        rows.append({
            "audit_id": s["audit_id"], "episode_id": s["episode_id"], "model": s["model"], "stratum": s["stratum"],
            "weight": s["weight"], **{k: c.get(k, scored.get(k)) for k in CONDITION},
            "question": rec["question"], "gold": gold_text(rec),
            "scorer_final_answer": s["scorer_final_answer"], "scorer_correct": scored["correct"],
            "stated_completeness": scored["stated_completeness"] if completeness else "",
            "disclosure_flag": scored["disclosure_flag"], "evidence_seen": scored["evidence_seen"],
            "calls_summary": calls_summary(rec), "final_text": rec["final_text"],
        })
    return pd.DataFrame(rows, columns=COLUMNS).sort_values("audit_id")


STYLE = """
:root { --bg: #ffffff; --fg: #1d1d1f; --muted: #5f6368; --line: #d9d9de; --card: #f7f7f9; --accent: #0b57d0; }
@media (prefers-color-scheme: dark) { :root { --bg: #161618; --fg: #ececf0; --muted: #a0a0a8; --line: #3a3a40;
  --card: #1f1f23; --accent: #8ab4f8; } }
body { background: var(--bg); color: var(--fg); font: 15px/1.5 -apple-system, "Segoe UI", sans-serif;
  max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; } .muted { color: var(--muted); }
section { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin: 18px 0; }
section h2 { font-size: 16px; margin: 0 0 8px; } table { border-collapse: collapse; width: 100%; }
td { padding: 3px 8px 3px 0; vertical-align: top; } td.k { color: var(--muted); width: 190px; white-space: nowrap; }
pre { white-space: pre-wrap; word-break: break-word; background: var(--bg); border: 1px solid var(--line);
  border-radius: 6px; padding: 10px; margin: 6px 0; font: 13px/1.45 ui-monospace, Menlo, monospace; }
.verdict { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line); }
.box { display: inline-block; margin-right: 18px; } nav a { color: var(--accent); margin-right: 8px; }
"""


def verdicts_path(out: Path) -> Path:
    name = out.name.replace("worksheet", "verdicts") if "worksheet" in out.name else f"{out.name}_verdicts"
    return out.with_name(name + ".csv")


def to_html(table: pd.DataFrame, title: str, source: str, verdicts_name: str = "the verdicts file",
            more: dict[int, list[tuple[str, str]]] | None = None) -> str:
    e = lambda v: html.escape("" if pd.isna(v) else str(v))  # noqa: E731
    counts = table.groupby(["model", "stratum"]).size().unstack(fill_value=0)
    parts = [(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
              f"content='width=device-width, initial-scale=1'><title>{e(title)}</title><style>{STYLE}</style></head><body>"),
             f"<h1>{e(title)}</h1><p class='muted'>{e(source)}</p>",
             (f"<p>Record each verdict in <code>{e(verdicts_name)}</code> beside this file (audit_id, verdict, note): "
              "<b>agree</b> if the scorer's correctness reading "
              "(<code>correct</code>) is right for the reply, <b>disagree</b> if it is wrong, <b>unsure</b> otherwise; "
              "add a note for every disagree or unsure. The other parsed fields are shown for context.</p>"),
             counts.to_html(border=0), "<nav>" + "".join(f"<a href='#a{int(i)}'>{int(i)}</a>" for i in table["audit_id"]) + "</nav>"]
    for _, r in table.iterrows():
        condition = ", ".join(f"{k}={e(r[k])}" for k in CONDITION if not pd.isna(r[k]) and str(r[k]) != "")
        parsed = f"correct={e(r['scorer_correct'])}; disclosure_flag={e(r['disclosure_flag'])}"
        if str(r["stated_completeness"]) not in ("", "nan"):
            parsed += f"; stated_completeness={e(r['stated_completeness'])}"
        added = dict((more or {}).get(int(r["audit_id"]), []))
        gold_cell = e(r["gold"]) if str(r["gold"]).startswith("rule: ") else f"<code>{e(r['gold'])}</code>"
        extra_rows = "".join(f"<tr><td class='k'>{e(k)}</td><td><code>{e(v)}</code></td></tr>" for k, v in added.items())
        parts.append(
            f"<section id='a{int(r['audit_id'])}'><h2>Audit {int(r['audit_id'])} · {e(r['model'])} · {e(r['stratum'])}</h2><table>"
            f"<tr><td class='k'>episode</td><td><code>{e(r['episode_id'])}</code> (weight {e(r['weight'])})</td></tr>"
            f"<tr><td class='k'>condition</td><td>{condition}</td></tr>"
            f"<tr><td class='k'>question</td><td>{e(r['question'])}</td></tr>"
            f"<tr><td class='k'>gold answer</td><td>{gold_cell}</td></tr>"
            f"<tr><td class='k'>scorer read</td><td><code>{e(r['scorer_final_answer'])}</code></td></tr>"
            f"<tr><td class='k'>parsed fields</td><td>{parsed}; rows the answer needed seen: {e(r['evidence_seen'])}</td></tr>"
            f"{extra_rows}</table><div class='muted'>calls</div><pre>{e(r['calls_summary'])}</pre>"
            f"<div class='muted'>final text</div><pre>{e(r['final_text'])}</pre>"
            "<div class='verdict'><span class='box'>☐ agree</span><span class='box'>☐ disagree</span>"
            "<span class='box'>☐ unsure</span> note: ____________________</div></section>")
    parts.append("</body></html>")
    return "\n".join(parts)


KEY_COLUMNS = ["audit_id", "episode_id", "model", "stratum", "weight", *CONDITION]
BLIND_NOTE = ("Blinding is partial: the wording of a reply, a COMPLETENESS line, or a reply's mention of a 'more' flag, "
              "a cursor or a page can still point to the model or the condition.")


def blinded(table: pd.DataFrame, more: dict[int, list[tuple[str, str]]]) -> pd.DataFrame:
    """The worksheet without model, condition, stratum, weight, episode id, calls or retrieval fields; the
    scorer's reading, and the served rows or ids it took, stay."""
    rows = []
    for _, r in table.iterrows():
        added = dict(more.get(int(r["audit_id"]), []))
        rows.append({"audit_id": r["audit_id"], "question": r["question"], "gold": r["gold"],
                     "scorer_final_answer": r["scorer_final_answer"], "scorer_correct": r["scorer_correct"],
                     "disclosure_flag": r["disclosure_flag"],
                     "scorer_detail": " | ".join(f"{k}: {v}" for k, v in added.items()), "final_text": r["final_text"]})
    return pd.DataFrame(rows)


def to_html_blinded(view: pd.DataFrame, title: str, source: str, verdicts_name: str) -> str:
    e = lambda v: html.escape("" if pd.isna(v) else str(v))  # noqa: E731
    parts = [(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
              f"content='width=device-width, initial-scale=1'><title>{e(title)}</title><style>{STYLE}</style></head><body>"),
             f"<h1>{e(title)}</h1><p class='muted'>{e(source)} {e(BLIND_NOTE)}</p>",
             (f"<p>Record each verdict in <code>{e(verdicts_name)}</code> (audit_id, verdict, note): <b>agree</b> if the "
              "scorer's correctness reading (<code>correct</code>) is right for the reply, <b>disagree</b> if it is wrong, "
              "<b>unsure</b> otherwise; add a note for every disagree or unsure.</p>"),
             "<nav>" + "".join(f"<a href='#a{int(i)}'>{int(i)}</a>" for i in view["audit_id"]) + "</nav>"]
    for _, r in view.iterrows():
        detail = "".join(f"<tr><td class='k'>{e(k)}</td><td><code>{e(v)}</code></td></tr>"
                         for k, v in (item.split(": ", 1) for item in str(r["scorer_detail"]).split(" | ") if ": " in item))
        gold_cell = e(r["gold"]) if str(r["gold"]).startswith("rule: ") else f"<code>{e(r['gold'])}</code>"
        parts.append(
            f"<section id='a{int(r['audit_id'])}'><h2>Audit {int(r['audit_id'])}</h2><table>"
            f"<tr><td class='k'>question</td><td>{e(r['question'])}</td></tr>"
            f"<tr><td class='k'>gold answer</td><td>{gold_cell}</td></tr>"
            f"<tr><td class='k'>scorer read</td><td><code>{e(r['scorer_final_answer'])}</code></td></tr>"
            f"<tr><td class='k'>parsed fields</td><td>correct={e(r['scorer_correct'])}; disclosure_flag={e(r['disclosure_flag'])}</td></tr>"
            f"{detail}</table><div class='muted'>final text</div><pre>{e(r['final_text'])}</pre>"
            "<div class='verdict'><span class='box'>☐ agree</span><span class='box'>☐ disagree</span>"
            "<span class='box'>☐ unsure</span> note: ____________________</div></section>")
    parts.append("</body></html>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sample_csv")
    p.add_argument("raw", nargs="+", help="raw episode logs (files or directories)")
    p.add_argument("--out", required=True, help="path without extension; writes .html, .csv and the verdicts file")
    p.add_argument("--html-only", action="store_true", help="rewrite only the HTML; leave the CSV and the verdicts file as they are")
    p.add_argument("--blinded", action="store_true",
                   help="write only <out>_blinded.html, <out>_blinded.csv and the key file (model, condition, stratum, weight "
                   "per audit id: \"worksheet\" in the name becomes \"key\"); the worksheet and verdicts files are not touched")
    args = p.parse_args(argv)
    sample_path = Path(args.sample_csv)
    by_id = records_by_id(args.raw)
    sample = pd.read_csv(sample_path)
    table = build(sample, by_id)
    more = {int(a): extras(by_id[eid]) for a, eid in zip(sample["audit_id"], sample["episode_id"], strict=True)}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    verdicts = verdicts_path(out)
    if args.blinded:
        view = blinded(table, more)
        base = out.with_name(out.name + "_blinded")
        key = out.with_name((out.name.replace("worksheet", "key") if "worksheet" in out.name else out.name + "_key") + ".csv")
        view.to_csv(base.with_suffix(".csv"), index=False)
        base.with_suffix(".html").write_text(to_html_blinded(
            view, "Correctness audit worksheet (blinded)",
            f"{len(view)} replies. Model, condition, stratum, weight and episode id are in {key.name}, not here.", verdicts.name))
        table[KEY_COLUMNS].to_csv(key, index=False)
        print(f"wrote {base.with_suffix('.html')}, {base.with_suffix('.csv')} and {key}")
        return
    digest = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    title = f"Correctness audit worksheet: {', '.join(sorted(table['model'].unique()))}"
    out.with_suffix(".html").write_text(to_html(table, title, f"{len(table)} replies from {sample_path.name} "
                                                              f"(sha256 {digest[:16]}…), drawn with the sampler's manifest beside it",
                                                verdicts.name, more))
    if args.html_only:
        print(f"wrote {out.with_suffix('.html')} only")
        return
    table.to_csv(out.with_suffix(".csv"), index=False)
    if verdicts.exists():  # never overwrite verdicts already entered
        print(f"kept the existing {verdicts}")
    else:
        pd.DataFrame({"audit_id": sorted(table["audit_id"]), "verdict": "", "note": ""}).to_csv(verdicts, index=False)
    print(f"wrote {len(table)} replies -> {out.with_suffix('.html')}, {out.with_suffix('.csv')} and {verdicts}")


if __name__ == "__main__":
    main()
