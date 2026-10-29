"""Episode-level metrics and the `fplp score` command.

follow_up          any request beyond the first page of the target query (attempts count)
fetch_needed       from the condition: more rows exist and the task needs them
responsive_follow_up  follow_up counting only calls issued after page 1 came back, so a blind parallel
                   fetch made before any signal was seen does not count (sensitivity analysis)
followup_calls     number of follow-up requests on the target query (extra calls, a cost)
missed_fetch       1 - follow_up where fetch_needed (blank otherwise)
extra_fetch        follow_up where not fetch_needed: a full or short last page, or a page-1-sufficient
                   task (blank where fetch_needed). Called "unnecessary" in the registered draft; it can
                   be a sensible check of a truthful terminal signal, so it is reported as a cost
own_small_page     the model asked for fewer rows than the page limit on its first call, so a one-page
                   extent is no longer one page for it; left out of fetch tests (amendment 1)
completion         the agent retrieved every row of the target result set
correct            final answer matches gold
evidence_seen      every row the answer depends on was retrieved (every row, for tasks whose answer
                   depends on all of them); an answer can be incomplete in this sense even when correct
justified_correct  correct, and for needs-all tasks evidence_seen
                   (rules out lucky guesses; allows valid shortcuts such as jumping to the last page)
disclosure_flag    rule-based (`disclosure_flag()`): the final reply says, in prose (the COMPLETENESS
                   line aside), that the result may be incomplete
disclosed          disclosure_flag on incomplete answers (evidence_seen = 0; blank otherwise)
hedged             disclosure_flag on answers with their evidence seen: false disclosure (blank otherwise)
disclosure_stratum for incomplete needs-all answers, whether disclosure was warranted from the agent's
                   point of view: "warranted" (a truthful signal said more rows exist, or a full page
                   came back with no signal under a stated limit and documented pagination),
                   "api_said_done" (a false end signal), "visible_conflict" (a false end beside a field
                   that contradicts it), "short_page" (a short page with no signal looks
                   final), "no_cue" (a full page with no signal, the limit hidden or pagination
                   undocumented); blank otherwise (amendment 1)
settled_on_page1   an exists "yes" whose qualifying row is on page 1, so no fetch is needed whatever the
                   signal says (only in the one-page extents); left out of fetch analyses
speculative_fetch  a later page was requested in the same turn as the first page, before any signal was seen
stated_completeness  the COMPLETENESS line under the completeness answer format
empty_reply        the last turn had no text and no tool call: a protocol failure, excluded from analysis
truncated          some turn's output was cut at the model's max_tokens

The disclosure patterns are validated against two authors' labels on a random sample of replies
(`fplp disclosure`); if the flag's precision or recall is below 0.80, disclosure is reported from
the hand labels instead. No LLM judge is used. The seeded vocabularies avoid words the patterns
match ("partial", "incomplete").

`fplp score --config` keeps only the episodes that config plans under the current model settings,
drops duplicates, and reports missing episodes and mixed code versions.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

CONDITION_FIELDS = [
    "arm", "signal_form", "extent", "task_need", "task_type", "item", "placement", "conflict",
    "documented", "limit_stated", "phrasing", "answer_format", "page_limit", "replicate", "seed",
    "more_exists", "fetch_needed", "doc_wording",
]
CONDITION_DEFAULTS = {
    "extent": "more_full", "limit_stated": True, "phrasing": "neutral", "answer_format": "final_line",
    "doc_wording": "default",
}

# Explicit statements that the answer may be incomplete. Narration of the paging process ("the first
# page returned 20 orders", "there were no more results") is deliberately not matched: a check run
# showed such phrases in replies that asserted completeness. "At least N" is not matched either: it
# is often a plain lower bound in a complete answer. Negations ("weren't truncated", "no truncation",
# "nothing is truncated") assert completeness, so they are excluded.
_NOUNS = r"(?:results|orders|products|tickets|items|rows|records|entries|data|pages?)"
_NEG = r"(?<!not )(?<!n't )(?<!never )(?<!no )(?<!nothing is )(?<!nothing was )"
DISCLOSURE_PATTERNS = [
    _NEG + r"\bincomplete\b",
    r"\bpartial (?:list|results?|answer|data|view|set|count)\b",
    _NEG + r"\btruncat",
    r"\bnot (?:the (?:full|complete|entire)|a complete)\b",
    # "there may be more (orders)", but not "may have more than one item" or "could be more expensive"
    rf"\b(?:may|might|could) (?:be|have) more(?: {_NOUNS})?(?=\s*(?:[.,;:!)]|$)|\s+(?:that|which|I|beyond|on|in|not)\b)",
    rf"\b(?:may|might|could) (?:be|exist|have) (?:additional|further|other) {_NOUNS}",
    rf"(?<!no )\b(?:additional|further|more|other) {_NOUNS} (?:may|might|could) (?:exist|be available|remain)\b",
    rf"\bmore (?:{_NOUNS} )?(?:may|might|could) (?:be available|exist)\b",
    r"\b(?:may|might|could) not (?:be|include|reflect|contain|cover|show) (?:all|every|the (?:full|complete|entire))\b",
    r"\b(?:may|might) not be (?:complete|exhaustive)\b",
    r"\b(?:may|might|could) be (?:partial|an undercount|understated)\b",
    r"\b(?:count|number|total|answer|list|figure)\b[^.\n]{0,40}?\b(?:may|might|could) be (?:higher|larger|greater)\b",
    # "there are additional orders beyond this page", but not "check if there are more pages beyond this"
    rf"(?<!if )(?<!whether )\bthere (?:are|may be|might be|could be) (?:additional|further|more) {_NOUNS} beyond\b",
    (rf"\bbefore (?:any )?(?:additional|further|more|remaining|other|the next) (?:pages?|{_NOUNS})\b"
     r"[^.\n]{0,30}\b(?:could|can|were|was) (?:be )?(?:examined|checked|retrieved|fetched|reviewed|seen)"),
    r"\bbased on the (?:retrieved|first|single) page\b",
    rf"\bbased on the {_NOUNS} (?:retrieved|seen|fetched|checked|reviewed) so far\b",
    r"\bbased on the (?:data|results|information) (?:retrieved|seen|fetched|available) so far\b",
    (rf"\bonly (?:saw|see|seen|retrieved|fetched|checked|looked at|reviewed|have|had|covers?|covered|includes?|included)"
     rf" (?:the )?(?:first (?:page|\d+ {_NOUNS})|one page|1 page|a single page|page 1)\b"),
    rf"\b(?:covers?|includes?|reflects?|is based on) only (?:the )?(?:first page|page 1|first \d+ {_NOUNS})\b",
    rf"\bonly (?:the )?first \d+ {_NOUNS}\b",
    r"\bbased (?:only|solely) on (?:the )?(?:first page|page 1)\b",
    r"\bbased on (?:the )?(?:first page|page 1) (?:only|alone)\b",
    r"\b(?:can(?:no|')t|cannot|could(?:n't| not)|unable to) (?:be (?:fully )?(?:sure|certain)|guarantee)\b",
    r"\bmore (?:results|orders|products|tickets|items) (?:available|not shown|to (?:fetch|retrieve|load))\b",
    (r"\b(?:did not|didn't|have not|haven't|was not able to|wasn't able to|could not|couldn't|cannot|can't|unable to)"
     r" (?:check|fetch|retrieve|review|see|look at|confirm|verify)\b[^.\n]{0,40}"
     r"\b(?:remaining|rest|later|additional|further|full|complete|entire|all)\b"),
    r"\bstopped (?:after|at) (?:the )?(?:first page|page 1)\b",
    r"\bbeyond (?:the )?(?:first page|page 1)\b[^.\n]{0,30}\bnot (?:retrieved|fetched|checked|shown|seen|included)\b",
]
_DISCLOSURE = re.compile("|".join(DISCLOSURE_PATTERNS), re.IGNORECASE)
# "20 of 87" discloses only when the first number is smaller ("20 of 20" asserts completeness), and
# not when the same sentence says the rest was fetched ("20 of 87 on page 1, then fetched the rest").
_N_OF_M = re.compile(
    r"\b(?:showing|showed|shown|returned|retrieved|fetched|seen|saw) (?:only )?(\d+) of (\d+)\b"
    r"(?![^.\n]*\b(?:fetched|retrieved|requested|got|pulled|loaded)\b[^.\n]*\b(?:rest|remaining|next|others?|pages?)\b)",
    re.IGNORECASE)
# The answer-format arm's COMPLETENESS line, tolerating markdown emphasis ("**COMPLETENESS:** partial").
_COMPLETENESS = re.compile(r"COMPLETENESS[\s*_]*:[\s*_]*(complete|partial|unknown)", re.IGNORECASE)
# Only the structured field is removed; a line a model writes on its own ("Completeness: only the
# first page was checked, so there may be more") is prose and stays.
_COMPLETENESS_LINE = re.compile(r"^[\s*_#>-]*COMPLETENESS[\s*_]*:[\s*_]*(?:complete|partial|unknown)[\s*_.]*$",
                                re.IGNORECASE | re.MULTILINE)


def prose(text: str) -> str:
    """The reply without its COMPLETENESS line, so the flag (and the hand labels) judge only what the
    model wrote in its own words; the line itself is scored as stated_completeness."""
    return _COMPLETENESS_LINE.sub("", text)


def disclosure_flag(text: str) -> bool:
    """Rule-based: the reply says, in prose, that the answer may be incomplete."""
    text = normalize(prose(text))
    return bool(_DISCLOSURE.search(text)) or any(int(n) < int(m) for n, m in _N_OF_M.findall(text))


_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe63\uff0d"), "-")
_SPACES = dict.fromkeys(map(ord, "\u00a0\u2007\u2009\u202f"), " ")
_QUOTES = {**dict.fromkeys(map(ord, "\u2018\u2019\u201b\u2032"), "'"), **dict.fromkeys(map(ord, "\u201c\u201d"), '"')}


def normalize(text: str) -> str:
    """Map typographic dashes to "-", special spaces to " " and curly quotes to straight ones (models
    emit e.g. "SKU\u201146945" and "weren\u2019t"), and drop thin or no-break spaces used as thousands
    separators ("10\u202f288.72")."""
    text = re.sub(r"(?<=\d)[\u00a0\u2009\u202f](?=\d{3}\b)", "", text)
    return text.translate(_DASHES).translate(_SPACES).translate(_QUOTES)


def final_answer(text: str) -> str:
    """Text after the last "FINAL ANSWER:" (up to a COMPLETENESS line), or the whole reply."""
    text = normalize(text)
    matches = list(re.finditer(r"FINAL ANSWER:\s*", text, re.IGNORECASE))
    answer = text[matches[-1].end() :] if matches else text
    return re.split(r"COMPLETENESS:", answer, flags=re.IGNORECASE)[0].strip()


def stated_completeness(text: str) -> str | None:
    found = _COMPLETENESS.findall(normalize(text))
    return found[-1].lower() if found else None


# Numbers in an answer line that are not the answer: record IDs, ISO dates, page numbers, and the
# total in "7 of 40", "out of 40" or "of the 40 orders".
_NOT_ANSWER = re.compile(
    r"\b(?:ORD|TCK|SKU)-\d+\b|\b\d{4}-\d{1,2}-\d{1,2}\b|\bpages? \d+(?:\s*(?:of|/)\s*\d+)?"
    r"|(?<=\d)\s+(?:out )?of (?:the |all )?\d[\d,]*|\bout of (?:the |all )?\d[\d,]*|\bof (?:the|all) \d[\d,]*",
    re.IGNORECASE)
_ZERO = re.compile(r"^\W*(?:none|no|zero|0)\b", re.IGNORECASE)


def _number(text: str) -> float | None:
    text = _NOT_ANSWER.sub(" ", text.replace("$", ""))
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if m:
        return float(m.group().replace(",", ""))
    return 0.0 if _ZERO.search(text) else None  # "None" / "No orders" as a count


_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE),
     lambda m: datetime.strptime(f"{m[1][:3]} {m[2]} {m[3]}", "%b %d %Y").date()),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})\s+(\d{{4}})\b", re.IGNORECASE),
     lambda m: datetime.strptime(f"{m[2][:3]} {m[1]} {m[3]}", "%b %d %Y").date()),
]


def _first_date(text: str) -> date | None:
    """Earliest-positioned date in the text, as ISO (2026-05-27) or written (May 27, 2026 / 27 May 2026)."""
    found = []
    for pattern, build in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                found.append((m.start(), build(m)))
            except ValueError:
                continue
    return min(found)[1] if found else None


def is_correct(gold: dict, text: str) -> bool:
    answer = final_answer(text)
    kind = gold["answer_type"]
    if kind == "count":
        n = _number(answer)
        return n is not None and n == gold["value"]
    if kind == "amount":
        n = _number(answer)
        return n is not None and abs(n - gold["value"]) <= 0.01
    if kind == "date":
        d = _first_date(answer) or _first_date(normalize(text))
        return d is not None and d.isoformat() == gold["value"]
    if kind == "yes_no":
        # A leading yes/no decides ("No, ... yes" is no); otherwise the answer must contain exactly
        # one of the two words, so "yes or no cannot be determined" is not read as an answer.
        lead = re.match(r"\W*(yes|no)\b", answer, re.IGNORECASE)
        found = {w.lower() for w in re.findall(r"\b(yes|no)\b", answer, re.IGNORECASE)}
        said = lead.group(1).lower() if lead else (found.pop() if len(found) == 1 else None)
        return said == gold["value"]
    if kind in ("id_set", "sku_any"):
        # Models often list IDs in the reply and end with "FINAL ANSWER: listed above", so when the
        # final line holds no IDs, read them from the whole reply.
        pattern = r"TCK-\d+" if kind == "id_set" else r"SKU-\d+"
        ids = set(re.findall(pattern, answer.upper())) or set(re.findall(pattern, normalize(text).upper()))
        if kind == "id_set":
            return ids == set(gold["value"])
        return bool(ids) and ids <= set(gold["accepted"])
    raise ValueError(f"unknown answer type: {kind}")


def score_episode(rec: dict) -> dict:
    c = {**CONDITION_DEFAULTS, **rec["condition"]}
    c.setdefault("more_exists", c["extent"] in ("more_full", "more_short"))
    c.setdefault("fetch_needed", c["more_exists"] and c["task_need"] == "needs_all")
    target = [x for x in rec["calls"] if x["is_target"]]
    # A follow-up is a paging attempt (cursor or page > 1, even if it failed) or any call after the
    # first successful one that returns rows it did not, e.g. page 1 again with a larger limit. A
    # failed first attempt (say page 0) followed by page 1 is not a follow-up.
    def rows(x: dict) -> set[int]:
        return set(range(x["offset"], x["offset"] + x["n_rows"]))

    ok = [i for i, x in enumerate(target) if x["error"] is None and x["offset"] is not None]
    first_rows = rows(target[ok[0]]) if ok else set()
    is_followup = [bool(x["paging"] or (x["offset"] or 0) > 0) for x in target]
    for i in ok[1:]:
        is_followup[i] = is_followup[i] or not rows(target[i]) <= first_rows
    follow_up = any(is_followup)
    # Responsive: issued in a later turn than the first successful page 1 (calls without a recorded turn,
    # from older logs, count as responsive).
    first_turn_ok = target[ok[0]].get("turn") if ok else None
    responsive = any(f and (x.get("turn") is None or first_turn_ok is None or x["turn"] > first_turn_ok)
                     for f, x in zip(is_followup, target, strict=True))
    # A page past the first requested in the same turn as the first page was asked for before any
    # signal could be read (parallel calls), so it is speculative rather than a response to a signal.
    first_turn = min((x.get("turn", 0) for x in target), default=None)
    speculative = any((x["paging"] or (x["offset"] or 0) > 0) and x.get("turn") is not None
                      and x.get("turn") == first_turn for x in target)
    covered: set[int] = set()
    for x in target:
        if x["error"] is None and x["offset"] is not None:
            covered.update(range(x["offset"], x["offset"] + x["n_rows"]))
    completion = covered >= set(range(rec["n_items"]))
    correct = is_correct(rec["gold"], rec["final_text"])
    needs_all = c["task_need"] == "needs_all"
    if "evidence" in rec["gold"]:
        evidence = rec["gold"]["evidence"]
    else:  # logs written before the field existed: rebuild it (item generation is deterministic)
        from fplp.conditions import TASK_NEED, Condition
        from fplp.tasks.specs import build_episode

        known = rec["condition"]["task_type"] in TASK_NEED  # retired task types: every row
        evidence = build_episode(Condition.from_dict(rec["condition"])).gold.evidence if known else None
    evidence_seen = covered >= (set(range(rec["n_items"])) if evidence is None else set(evidence))
    flag = disclosure_flag(rec["final_text"])
    # An exists "yes" whose qualifying row is on page 1 (the whole set fits on one page in the last_*
    # extents) is settled without fetching, whatever the signal; fetch analyses leave it out.
    stratum = None
    if needs_all and not evidence_seen:
        if c.get("conflict") in ("visible_conflict_total", "visible_conflict_note"):
            stratum = "visible_conflict"   # the page contradicted its own end signal (H6 cells)
        elif c.get("conflict"):
            stratum = "api_said_done"
        elif c["signal_form"] != "none":
            stratum = "warranted"       # a truthful signal said more rows exist, and the agent stopped
        elif c["extent"] == "more_full":
            # a full page with no signal warrants doubt only when the interface says pages are capped
            # and paginated (stated limit, documented pagination)
            stratum = "warranted" if c["limit_stated"] and c.get("documented", True) else "no_cue"
        else:
            stratum = "short_page"      # a short page with no signal looks like the end
    page_limit = c.get("page_limit") or 20
    requested = target[ok[0]].get("limit") if ok else None
    settled = rec["condition"]["task_type"] == "exists" and rec["gold"]["value"] == "yes" \
        and bool(evidence) and min(evidence) < rec.get("first_page_size", min(c["page_limit"], rec["n_items"]))
    truncated = rec.get("truncated", any(t.get("stop_reason") in ("length", "max_tokens") for t in rec.get("turns", [])))
    needed = bool(c["fetch_needed"])
    return {
        "episode_id": rec["episode_id"],
        "model": rec["model"],
        **{k: c[k] for k in CONDITION_FIELDS},
        "n_items": rec["n_items"],
        "n_calls": len(rec["calls"]),
        "n_target_calls": len(target),
        # The page size the model asked for on its first successful call; below the page limit, the
        # one-page extents are no longer one page for that model (audit column, not a test input).
        "requested_limit": requested,
        "own_small_page": int(requested is not None and requested < page_limit),
        "follow_up": int(follow_up),
        "responsive_follow_up": int(responsive),
        "followup_calls": sum(is_followup),
        "speculative_fetch": int(speculative),
        "missed_fetch": int(not follow_up) if needed else None,
        "extra_fetch": None if needed else int(follow_up),
        "completion": int(completion),
        "evidence_seen": int(evidence_seen),
        "correct": int(correct),
        "justified_correct": int(correct and (evidence_seen or not needs_all)),
        "disclosure_flag": int(flag),
        "disclosed": None if evidence_seen else int(flag),
        "hedged": int(flag) if evidence_seen else None,
        "settled_on_page1": int(settled),
        "disclosure_stratum": stratum,
        "stated_completeness": stated_completeness(rec["final_text"]),
        "empty_reply": int(rec.get("empty_reply", not rec["final_text"].strip())),
        "truncated": int(truncated),
        "hit_cap": int(rec["hit_cap"]),
        "stop_reason": rec["stop_reason"],
        "tokens_in": rec["tokens_in"],
        "tokens_out": rec["tokens_out"],
        "cache_read": rec.get("cache_read", 0),
    }


def _episode_files(paths: list[str]) -> list[Path]:
    """Episode logs (.jsonl, or gzipped .jsonl.gz as in data/protocol-checks), without error logs."""
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            found = [*p.glob("*.jsonl"), *p.glob("*.jsonl.gz")]
            files.extend(sorted(f for f in found if ".errors." not in f.name))
        else:
            files.append(p)
    return files


def _read_records(files: list[Path]) -> tuple[list[dict], int]:
    """Every episode record, plus the number of unreadable lines (an interrupted write)."""
    records, bad = [], 0
    for f in files:
        with (gzip.open(f, "rt") if f.suffix == ".gz" else f.open()) as fh:
            for line in fh:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        bad += 1
    return records, bad


def select_records(records: list[dict], plan: dict[str, set[str]] | None,
                   snapshots: dict[str, str] | None = None) -> tuple[list[dict], list[str]]:
    """Keep one record per episode id, from retained task types, and (given a plan of episode ids per
    model) only planned episodes. Returns the kept records and report lines; warnings name mixed code
    versions or settings, which mean the episodes did not all come from the same harness."""
    from fplp.conditions import TASK_NEED

    seen: set[str] = set()
    kept, duplicates, retired, unplanned = [], 0, Counter(), Counter()
    for rec in records:
        if rec["episode_id"] in seen:
            duplicates += 1
            continue
        seen.add(rec["episode_id"])
        if rec["condition"]["task_type"] not in TASK_NEED:
            retired[rec["condition"]["task_type"]] += 1
        elif plan is not None and rec["episode_id"] not in plan.get(rec["model"], set()):
            unplanned[rec["model"]] += 1
        else:
            kept.append(rec)

    report = []
    if duplicates:
        report.append(f"dropped {duplicates} duplicate record(s) (same episode id; the first was kept)")
    if retired:
        report.append(f"dropped {sum(retired.values())} episode(s) of retired task types: {dict(retired)}")
    for model, n in sorted(unplanned.items()):
        report.append(f"WARNING {model}: dropped {n} episode(s) the config does not plan under the current "
                      "model settings (a changed setting, another run, or a model not in the config)")
    if plan is not None:
        have = Counter(r["model"] for r in kept)
        for model, ids in sorted(plan.items()):
            report.append(f"{model}: {have[model]} of {len(ids)} planned episodes scored, {len(ids) - have[model]} missing")
    versions = Counter((r.get("provenance") or {}).get("git_sha") or r.get("harness_version") for r in kept)
    if len(versions) > 1:
        report.append(f"WARNING episodes come from {len(versions)} code versions: {dict(versions)}")
    if dirty := sum(bool((r.get("provenance") or {}).get("git_dirty")) for r in kept):
        report.append(f"WARNING {dirty} episode(s) were run from a working tree with uncommitted changes")
    for model in sorted({r["model"] for r in kept}):
        keys = {r.get("config_key") for r in kept if r["model"] == model}
        if len(keys) > 1:
            report.append(f"WARNING {model}: episodes come from {len(keys)} different model settings")
        served = {t.get("served_model") for r in kept if r["model"] == model for t in r.get("turns", [])} - {None}
        if len(served) > 1:  # a router or provider swapped the model version mid-run
            report.append(f"WARNING {model}: turns were served by {len(served)} model versions: {sorted(served)}")
        expected = (snapshots or {}).get(model)
        if expected and served - {expected}:  # a version change since the snapshot was recorded (pilot)
            report.append(f"WARNING {model}: served {sorted(served - {expected})}, not the recorded snapshot {expected!r}")
    return kept, report


def _plan(config: str, models_file: str) -> dict[str, set[str]]:
    from fplp.conditions import DEFAULT_MAX_TOOL_CALLS, build_conditions, planned
    from fplp.config import ConfigError, load_models, load_run_config

    try:
        cfg = load_run_config(config, require_items=True)
        registry = load_models(models_file)
    except ConfigError as e:
        sys.exit(str(e))
    if not cfg.get("models"):
        sys.exit(f"{config}: no models listed")
    if missing := [m for m in cfg["models"] if m not in registry]:
        sys.exit(f"models not defined in {models_file}: {missing}")
    conditions = build_conditions(cfg)
    max_calls = cfg.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
    return {m: {eid for eid, _ in planned(registry[m], conditions, max_calls)} for m in cfg["models"]}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Score episode logs into one CSV row per episode.")
    parser.add_argument("inputs", nargs="+", help="episode .jsonl files or directories of them")
    parser.add_argument("--out", required=True, help="output CSV, e.g. data/processed/pilot.csv")
    parser.add_argument("--config", help="run config whose planned episodes to keep, e.g. configs/runs/main.yaml; "
                        "also reports missing episodes (use it for every confirmatory analysis)")
    parser.add_argument("--models-file", default="configs/models.yaml")
    args = parser.parse_args(argv)

    records, bad = _read_records(_episode_files(args.inputs))
    snapshots = None
    if args.config:
        from fplp.config import load_models

        snapshots = {name: m["snapshot"] for name, m in load_models(args.models_file).items() if m.get("snapshot")}
    records, report = select_records(records, _plan(args.config, args.models_file) if args.config else None, snapshots)
    if bad:
        report.insert(0, f"skipped {bad} unreadable line(s) (an interrupted write)")
    for line in report:
        print(line)
    rows = [score_episode(r) for r in records]
    if not rows:
        raise SystemExit("no episodes found")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"scored {len(rows)} episodes -> {out}")


if __name__ == "__main__":
    main()
