"""Check the rater's part-2 workbook against the original blinded worksheet, then write audit_verdicts_part2.csv.

  part2_workbook.py check   RATED.xlsx ORIGINAL.csv [--accept-retyped 6,8,...]
  part2_workbook.py convert RATED.xlsx ORIGINAL.csv OUT.csv [--accept-retyped 6,8,...]

Columns are matched by name. audit_id, question, gold, scorer_final_answer, scorer_correct and final_text
must equal the original's text exactly. A cell Excel stored as a number is read as its digits (4.0 -> "4")
and listed; it matches only if that text equals the original's (a date gains a time and so differs). convert runs the check first and writes nothing
if any row differs. Agree -> agree; audit 17 (unsure in the workbook) -> agree with the rater's recorded
confirmation; the "Validation Notes" and "the rater Notes" columns are carried over verbatim (UTF-8).

--accept-retyped lists audit ids whose scorer_final_answer the lead author accepts as the spreadsheet's retyping
(decided 25 Oct 2026): each is accepted only if the cell holds the same value (a date with no time equal to the
original ISO date, or a number equal to the original's); any other difference still stops."""
import collections
import csv
import datetime as dt
import sys

import openpyxl

REQUIRED = ["audit_id", "question", "gold", "scorer_final_answer", "scorer_correct", "final_text"]
NOTE_COLS = ["Validation Notes", "the rater Notes"]
CONFIRM_17 = ("Rated unsure in the workbook; the rater confirmed on 2026-10-25 at about 15:40 EDT that the "
              "scorer's label is correct (first number 1 against gold 4; the hedge is a disclosure question, "
              "not a correctness one), so it is recorded as agree.")


def cell_text(v):
    """A cell as text, and whether Excel stored it as something other than text."""
    if v is None:
        return "", False
    if isinstance(v, str):
        return v, False
    if isinstance(v, bool):
        return str(v), True
    if isinstance(v, (int, float)):
        return (str(int(v)) if float(v).is_integer() else repr(v)), True
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(), True
    return str(v), True


def read_rated(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets = wb.sheetnames
    ws = wb[sheets[0]]
    rows = list(ws.iter_rows(values_only=True))
    header = [cell_text(h)[0].strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(c not in (None, "") for c in r)]
    return sheets, header, [dict(zip(header, r)) for r in body]


def same_value(v, original):
    """A retyped cell that holds the original's value: a date with no time, or an equal number."""
    if isinstance(v, dt.datetime):
        return v.time() == dt.time(0) and v.date().isoformat() == original
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            return float(original) == float(v)
        except ValueError:
            return False
    return False


def check(rated_path, original_path, accept=frozenset()):
    original = list(csv.DictReader(open(original_path, encoding="utf-8", newline="")))
    sheets, header, rated = read_rated(rated_path)
    print("sheets:", sheets, "(first one read)")
    print("rated columns:", header)
    print("original columns:", list(original[0]))
    problems = []
    if missing := [c for c in REQUIRED if c not in header]:
        problems.append(f"required column(s) missing: {missing}")
    if dup := [c for c, n in collections.Counter(header).items() if n > 1]:
        problems.append(f"duplicate column name(s): {dup}")
    print("rows:", len(rated), "vs", len(original))
    if problems:
        for p in problems: print("PROBLEM:", p)
        return None, False
    orig = {r["audit_id"]: r for r in original}
    ids = [cell_text(r["audit_id"])[0] for r in rated]
    if sorted(ids, key=lambda s: int(s) if s.isdigit() else -1) != sorted(orig, key=int):
        problems.append(f"audit ids differ from the original's 1..{len(orig)}: {ids}")
    differs, retyped, accepted = [], [], []
    for r in rated:
        aid = cell_text(r["audit_id"])[0]
        o = orig.get(aid)
        if o is None:
            continue
        for c in REQUIRED:
            text, typed = cell_text(r[c])
            if typed and c != "audit_id":
                retyped.append((aid, c, type(r[c]).__name__, text[:40], o[c][:40]))
            if text != o[c] and c == "scorer_final_answer" and aid in accept and same_value(r[c], o[c]):
                accepted.append((aid, c, type(r[c]).__name__, text, o[c]))
                continue
            if text != o[c]:
                # Excel turns CRLF into LF in a cell; say so rather than hide it
                kind = "line endings only" if text.replace("\r\n", "\n") == o[c].replace("\r\n", "\n") else "content"
                i = next((k for k, (x, y) in enumerate(zip(text, o[c])) if x != y), min(len(text), len(o[c])))
                differs.append((aid, c, kind, f"first difference at character {i}",
                                text[max(0, i - 20):i + 30], o[c][max(0, i - 20):i + 30]))
    others = [c for c in original[0] if c in header and c not in REQUIRED]
    other_diff = collections.defaultdict(list)
    for r in rated:
        aid = cell_text(r["audit_id"])[0]
        if aid in orig:
            for c in others:
                if cell_text(r[c])[0] != orig[aid][c]:
                    other_diff[c].append(aid)
    print("accepted as the spreadsheet's retyping of the same value:", len(accepted))
    for d in accepted: print("  ", d)
    if missing_accept := sorted(set(accept) - {a for a, *_ in accepted}, key=int):
        problems.append(f"--accept-retyped names audit ids with no such retyped cell: {missing_accept}")
    print("required-field differences:", len(differs))
    for d in differs: print("  ", d)
    print("required cells Excel stored as a number or date (listed; a match only if the text is equal):", len(retyped))
    for d in retyped: print("  ", d)
    for c, v in other_diff.items():
        print(f"other shared column differs (reported, not a stop): {c}: audit ids {v}")
    new_cols = [c for c in header if c not in original[0]]
    print("columns added by the rater:", new_cols)
    for p in problems: print("PROBLEM:", p)
    ok = not problems and not differs
    print("CHECK:", "every row matches" if ok else "STOP: a row differs from the original")
    return rated, ok


def convert(rated_path, original_path, out_path, accept=frozenset()):
    rated, ok = check(rated_path, original_path, accept)
    if not ok:
        sys.exit("nothing written")
    header = list(rated[0])
    if missing := [c for c in NOTE_COLS if c not in header]:
        sys.exit(f"notes column(s) not found: {missing}; nothing written")
    original_cols = next(csv.reader(open(original_path, encoding="utf-8", newline="")))
    rating_cols = [c for c in header if c not in original_cols and c not in NOTE_COLS]
    if len(rating_cols) != 1:
        sys.exit(f"expected one rating column besides the notes, found {rating_cols}; nothing written")
    rc = rating_cols[0]
    print("rating column:", repr(rc), dict(collections.Counter(cell_text(r[rc])[0] for r in rated)))
    out = []
    for r in rated:
        aid = int(cell_text(r["audit_id"])[0])
        rating = cell_text(r[rc])[0].strip().lower()
        if rating == "agree":
            verdict, note = "agree", ""
        elif aid == 17 and rating == "unsure":
            verdict, note = "agree", CONFIRM_17
        else:
            sys.exit(f"audit {aid}: rating {rating!r} has no recorded resolution; nothing written")
        out.append({"audit_id": aid, "verdict": verdict, "note": note,
                    "validation_notes": cell_text(r["Validation Notes"])[0].strip(),
                    "rater_notes": cell_text(r["the rater Notes"])[0].strip()})
    out.sort(key=lambda d: d["audit_id"])
    assert [d["audit_id"] for d in out] == list(range(1, len(out) + 1))
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {out_path}: {dict(collections.Counter(d['verdict'] for d in out))}; "
          f"validation notes {sum(bool(d['validation_notes']) for d in out)}, "
          f"the rater notes {sum(bool(d['rater_notes']) for d in out)}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    accept = frozenset()
    if "--accept-retyped" in args:
        i = args.index("--accept-retyped")
        accept = frozenset(x.strip() for x in args[i + 1].split(",") if x.strip())
        args = args[:i] + args[i + 2:]
    {"check": check, "convert": convert}[cmd](*args, accept=accept)
