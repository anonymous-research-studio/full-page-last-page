"""Checklist section 6 log checks, plus an independent re-derivation of the fetch measures (condition 2).

Read-only. Uses the frozen code only where the checklist says to (episode ids recompute with the
harness's own function; `prose()` for the COMPLETENESS check; `build_episode` to rebuild each episode's
rows and gold). Fetch measures and answers are re-derived from the raw arguments and outputs: rows are
located by their IDs in the rebuilt row list, not from the harness's `offset`/`n_rows`/`paging` fields.

  python log_checks.py <frozen checkout> <out dir>
"""

import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

A, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(A / "src"))
from fplp.conditions import Condition, config_key, episode_id  # noqa: E402
from fplp.metrics import prose  # noqa: E402
from fplp.tasks.specs import build_episode  # noqa: E402

RUNS = {  # run -> (raw log, scored csv)
    "gpt-oss-120b (main, reference)": ("data/raw/main/gpt-oss-120b.jsonl", "data/processed/main.csv"),
    "mistral-medium-3-5 (main)": ("data/raw/main/mistral-medium-3-5.jsonl", "data/processed/main.csv"),
    "claude-sonnet-5-5 (main)": ("data/raw/main/claude-sonnet-5-5.jsonl", "data/processed/main.csv"),
    "nemotron-3-super (exploratory)": ("data/raw/exploratory/nemotron-3-super.jsonl", "data/processed/exploratory.csv"),
    "gpt-oss-120b (robustness)": ("data/raw/robustness/gpt-oss-120b.jsonl", "data/processed/robustness.csv"),
}
ID_KEYS = ("order_id", "sku", "ticket_id")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—−﹘﹣－"), "-")
NUM_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
MONTHS = {m: i for i, m in enumerate("january february march april may june july august september october november "
                                     "december".split(), start=1)}


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").translate(DASHES)
    return s.replace(" ", " ").replace(" ", " ").replace("**", "").replace("`", "")


def final_part(text: str) -> str:
    t = norm_text(text)
    idx = [m.end() for m in re.finditer(r"final answer\s*:", t, re.I)]
    part = t[idx[-1]:] if idx else t
    return re.split(r"completeness\s*:", part, flags=re.I)[0].strip()


def ind_count(ans: str):
    a = re.sub(r"\b(ORD|TCK|SKU)-\d+\b", " ", ans, flags=re.I)
    a = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", a)
    a = re.sub(r"\b(of|out of)\s+\d+", " ", a, flags=re.I)
    a = re.sub(r"\bpages?\s+\d+(\s*(-|to|and)\s*\d+)?", " ", a, flags=re.I)
    m = re.search(r"\b\d+\b", a)
    if m:
        return int(m.group())
    for w in re.findall(r"[a-z]+", a.lower()):
        if w in NUM_WORDS:
            return NUM_WORDS[w]
        if w in ("none", "no"):
            return 0
    return None


def ind_date(ans: str):
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", ans)
    if m:
        return "-".join(m.groups())
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", ans)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def ind_correct(gold: dict, text: str):
    ans, kind = final_part(text), gold["answer_type"]
    if kind == "count":
        v = ind_count(ans)
        return v is not None and v == gold["value"]
    if kind == "amount":
        m = re.search(r"-?\$?\s*(\d[\d,]*\.?\d*)", ans)
        return bool(m) and abs(float(m.group(1).replace(",", "")) - gold["value"]) <= 0.01
    if kind == "date":
        return ind_date(ans) == gold["value"] or (ind_date(ans) is None and ind_date(norm_text(text)) == gold["value"])
    if kind == "yes_no":
        lead = re.match(r"\W*(yes|no)\b", ans, re.I)
        words = {w.lower() for w in re.findall(r"\b(yes|no)\b", ans, re.I)}
        said = lead.group(1).lower() if lead else (words.pop() if len(words) == 1 else None)
        return said == gold["value"]
    pat = r"TCK-\d+" if kind == "id_set" else r"SKU-\d+"
    ids = set(re.findall(pat, ans.upper())) or set(re.findall(pat, norm_text(text).upper()))
    return ids == set(gold["value"]) if kind == "id_set" else (bool(ids) and ids <= set(gold["accepted"]))


def page_rows(output: str):
    """The rows a call returned, as dicts, and the signal fields, from its raw JSON output."""
    try:
        o = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return None, {}
    if not isinstance(o, dict) or "error" in o:
        return None, o if isinstance(o, dict) else {}
    rows = next((v for v in o.values() if isinstance(v, list) and all(isinstance(r, dict) for r in v)), [])
    return rows, {k: v for k, v in o.items() if not isinstance(v, list)}


def is_target_ind(call: dict, spec) -> bool:
    if call["tool"] != spec.target_tool:
        return False
    for k, v in spec.target_args.items():
        got = str(call["arguments"].get(k, "")).strip().lower()
        if str(v).strip().lower() not in got:
            return False
    return True


def paging_attempt(args: dict) -> bool:
    cur = args.get("cursor")
    if cur not in (None, ""):
        return True
    try:
        return int(args.get("page", 1)) > 1 or int(args.get("offset", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


report, per_run = [], {}
for run, (raw, scored_csv) in RUNS.items():
    scored = pd.read_csv(A / scored_csv).set_index("episode_id")
    recs = [json.loads(line) for line in open(A / raw)]
    model = recs[0]["model"]
    c = collections.Counter()
    ids = collections.Counter(r["episode_id"] for r in recs)
    serving = collections.Counter()
    page1 = collections.defaultdict(set)
    q_gold = collections.defaultdict(set)
    later_pages = collections.Counter()
    untruthful = []
    continue_how = collections.Counter()
    other_routes = collections.Counter()
    multi_turns = 0
    fetch_mismatch = collections.defaultdict(list)
    target_mismatch = 0
    answer_diff = collections.defaultdict(list)
    forced = []
    residual = []
    small_first = 0
    for r in recs:
        cond = Condition.from_dict(r["condition"])
        # 1. ids recompute
        c["id_recomputes"] += episode_id(r["model_config"], cond, r["max_tool_calls"]) == r["episode_id"]
        c["config_key_recomputes"] += config_key(r["model_config"], r["max_tool_calls"]) == r["config_key"]
        # 3. serving
        for t in r["turns"]:
            serving[(t.get("served_by"), t.get("served_model"))] += 1
            c["turns"] += 1
            c["turn_snapshot_mismatch"] += t.get("served_model") != r["model_config"].get("snapshot")
        spec = build_episode(cond)
        pos = {row[k]: i for i, row in enumerate(spec.rows) for k in ID_KEYS if k in row}
        n_items = len(spec.rows)
        c["n_items_match"] += n_items == r["n_items"]
        # 5. same rows (page 1 at the full page limit) and the same question and gold
        key = (cond.task_type, cond.item, cond.extent.value if hasattr(cond.extent, "value") else cond.extent)
        q_gold[key].add((r["question"], json.dumps(r["gold"], sort_keys=True)))
        target = [x for x in r["calls"] if is_target_ind(x, spec)]
        target_mismatch += sum(is_target_ind(x, spec) != bool(x["is_target"]) for x in r["calls"])
        for x in r["calls"]:
            if not is_target_ind(x, spec):
                other_routes[x["tool"]] += 1
        turns_calls = collections.Counter(x.get("turn") for x in r["calls"])
        multi_turns += sum(1 for n in turns_calls.values() if n > 1)
        # independent fetch measures
        seen_sets, first_ok, first_ok_turn = [], None, None
        is_fu = []
        for x in target:
            rows, sig = page_rows(x["output"])
            p = sorted(pos[row[k]] for row in (rows or []) for k in ID_KEYS if k in row and row[k] in pos)
            rowset = set(p)
            fu = paging_attempt(x["arguments"]) or bool(p and p[0] > 0)
            if rows is not None and first_ok is None:
                first_ok, first_ok_turn = rowset, x.get("turn")
                lim = x["arguments"].get("limit")
                if p and p[0] == 0 and (lim is None or int(lim) >= 20):
                    page1[key].add(json.dumps(rows, sort_keys=True))
                if lim is not None and int(lim) < 20:
                    small_first += 1
            elif rows is not None and not rowset <= (first_ok or set()):
                fu = True
            is_fu.append((fu, x.get("turn")))
            if rows is not None:
                seen_sets.append(rowset)
            # 6. later pages truthful in conflict cells
            if r["condition"].get("conflict") and rows and p and p[0] > 0:
                later_pages["later pages"] += 1
                end = p[-1] + 1
                ok = True
                if "has_more" in sig:
                    ok &= sig["has_more"] == (end < n_items)
                if "next_cursor" in sig:
                    ok &= (sig["next_cursor"] not in (None, "")) == (end < n_items)
                if "total_count" in sig:
                    ok &= sig["total_count"] == n_items
                for v in sig.values():
                    if isinstance(v, str):
                        m = re.search(r"of (\d+)", v)
                        if m:
                            ok &= int(m.group(1)) == n_items
                later_pages["truthful"] += ok
                if not ok:
                    untruthful.append(r["episode_id"])
        if r["condition"].get("conflict"):
            fus = [x for x, (f, _) in zip(target, is_fu, strict=True) if f]
            if fus:
                a = fus[0]["arguments"]
                continue_how["cursor" if a.get("cursor") not in (None, "") else f"page={a.get('page')}"] += 1
        covered = set().union(*seen_sets) if seen_sets else set()
        ev = spec.gold.evidence
        ind = {
            "follow_up": int(any(f for f, _ in is_fu)),
            "responsive_follow_up": int(any(f and (t is None or first_ok_turn is None or t > first_ok_turn) for f, t in is_fu)),
            "speculative_fetch": int(any((paging_attempt(x["arguments"])) and x.get("turn") is not None
                                         and x.get("turn") == min((y.get("turn", 0) for y in target), default=None)
                                         for x in target)),
            "evidence_seen": int(covered >= (set(range(n_items)) if ev is None else set(ev))),
        }
        s = scored.loc[r["episode_id"]] if r["episode_id"] in scored.index else None
        if s is None:
            c["not_in_scored"] += 1
        else:
            for k, v in ind.items():
                if int(s[k]) != v:
                    fetch_mismatch[k].append(r["episode_id"])
            # 10. independent answer extraction
            if int(ind_correct(r["gold"], r["final_text"])) != int(s["correct"]):
                answer_diff[r["gold"]["answer_type"]].append(r["episode_id"])
            # 11. forced final answers
            if int(s["hit_cap"]):
                last = r["turns"][-1]
                forced.append((r["episode_id"], bool((last.get("text") or "").strip()), len(last.get("tool_calls") or [])))
        # 12. COMPLETENESS lines left after prose()
        left = prose(r["final_text"] or "")
        if re.search(r"completeness\s*:", left, re.I):
            residual.append(r["episode_id"])
    sub = scored[scored["model"] == model] if "model" in scored else scored
    sub = sub[sub.index.isin([r["episode_id"] for r in recs])]
    prov = collections.Counter((r["provenance"]["git_sha"][:7], r["provenance"].get("git_dirty")) for r in recs)
    per_run[run] = dict(
        episodes=len(recs), unique_ids=len(ids), ids_recompute=c["id_recomputes"], config_key_recomputes=c["config_key_recomputes"],
        n_items_match=c["n_items_match"], provenance={str(k): v for k, v in prov.items()}, turns=c["turns"], turn_snapshot_mismatch=c["turn_snapshot_mismatch"],
        serving={str(k): v for k, v in serving.most_common(5)},
        protocol={k: int(sub[k].sum()) for k in ("empty_reply", "truncated", "hit_cap") if k in sub},
        refusals=int(sub["refusal"].sum()) if "refusal" in sub else "column absent",
        same_rows_groups=len(page1), same_rows_differing=sum(len(v) > 1 for v in page1.values()),
        question_gold_groups=len(q_gold), question_gold_differing=sum(len(v) > 1 for v in q_gold.values()),
        later_pages_conflict=dict(later_pages), untruthful_later_pages=untruthful[:5], continue_after_false_end=dict(continue_how),
        other_routes=dict(other_routes), target_flag_mismatch=target_mismatch,
        small_first_calls=small_first, own_small_page_scored=int(sub["own_small_page"].sum()),
        multi_call_turns=multi_turns, speculative_scored=int(sub["speculative_fetch"].sum()),
        fetch_mismatch={k: (len(v), v[:3]) for k, v in fetch_mismatch.items()},
        answer_diff={k: (len(v), v[:6]) for k, v in answer_diff.items()},
        forced_final=forced, completeness_residual=(len(residual), residual[:5]),
    )
    print(run, json.dumps(per_run[run], default=str, indent=None)[:4000], flush=True)
(OUT / "log_checks.json").write_text(json.dumps(per_run, default=str, indent=1))
