"""Print episode transcripts for qualitative review: question, each turn, each tool call with
the output the model saw, the final answer, gold, and the scores.

Usage:
  uv run fplp show data/raw/pilot/<model>.jsonl --form none --need needs_all --n 3
  uv run fplp show data/raw/pilot/<model>.jsonl --id 3f2a9c... --max-output 0   # full outputs
"""

from __future__ import annotations

import argparse
import json
import random
import textwrap

from fplp.metrics import score_episode


def _clip(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return f"{text[:limit]} … [{len(text) - limit} more chars]"


def render(rec: dict, max_output: int) -> str:
    c, s = rec["condition"], score_episode(rec)
    lines = [
        "=" * 100,
        (
            f"{rec['episode_id']}  model={rec['model']}  arm={c['arm']}  form={c['signal_form']}  "
            f"task={c['task_type']} ({c['task_need']})  item={c['item']}  placement={c['placement']}  "
            f"conflict={c['conflict']}  documented={c['documented']}"
        ),
        f"rows={rec['n_items']}  first page={rec['first_page_size']}  target={rec['target']}",
        f"Q: {rec['question']}",
        "-" * 100,
    ]
    calls = iter(rec["calls"])
    for i, turn in enumerate(rec["turns"], 1):
        if turn.get("reasoning", "").strip():
            lines.append(f"[turn {i}] reasoning: {_clip(turn['reasoning'].strip(), max_output)}")
        if turn["text"].strip():
            lines.append(f"[turn {i}] assistant:")
            lines.extend("    " + ln for ln in textwrap.wrap(turn["text"], 96) or [""])
        for tc in turn["tool_calls"]:
            lines.append(f"[turn {i}] call {tc['name']}({json.dumps(tc['arguments'])})")
            call = next(calls, None)
            if call is None:
                lines.append("    -> not executed (tool-call cap)")
                continue
            meta = f"target={call['is_target']} offset={call['offset']} rows={call['n_rows']}"
            lines.append(f"    -> {meta}" + (f" error={call['error']}" if call["error"] else ""))
            lines.extend("       " + ln for ln in _clip(call["output"], max_output).splitlines())
    gold = rec["gold"]
    lines += [
        "-" * 100,
        f"gold: {gold['value'] if gold['value'] is not None else gold['accepted'][:5]}",
        (
            f"follow_up={s['follow_up']} completion={s['completion']} correct={s['correct']} "
            f"disclosure_flag={s['disclosure_flag']} hit_cap={s['hit_cap']} stop={s['stop_reason']} "
            f"tokens={s['tokens_in']}/{s['tokens_out']}"
        ),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jsonl")
    parser.add_argument("--id", help="episode_id prefix")
    parser.add_argument("--form")
    parser.add_argument("--task")
    parser.add_argument("--need", choices=["needs_all", "page1_sufficient"])
    parser.add_argument("--incomplete", action="store_true", help="only episodes that did not retrieve every row")
    parser.add_argument("--empty", action="store_true", help="only episodes that ended with an empty reply")
    parser.add_argument("--n", type=int, default=1, help="number of episodes to show (random sample)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-output", type=int, default=400, help="chars of each tool output; 0 = all")
    args = parser.parse_args(argv)

    with open(args.jsonl) as fh:
        recs = [json.loads(line) for line in fh if line.strip()]
    for rec in recs:
        rec.setdefault("episode_id", "?")

    def keep(r: dict) -> bool:
        c = r["condition"]
        return (
            (not args.id or r["episode_id"].startswith(args.id))
            and (not args.form or c["signal_form"] == args.form)
            and (not args.task or c["task_type"] == args.task)
            and (not args.need or c["task_need"] == args.need)
            and (not args.incomplete or not score_episode(r)["completion"])
            and (not args.empty or score_episode(r)["empty_reply"])
        )

    matched = [r for r in recs if keep(r)]
    print(f"{len(matched)} of {len(recs)} episodes match")
    for rec in random.Random(args.seed).sample(matched, min(args.n, len(matched))):
        print(render(rec, args.max_output))


if __name__ == "__main__":
    main()
