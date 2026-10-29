"""Returned disclosure labels (scripts/disclosure_labels.py): checks, conversion and the weighted estimates."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "disclosure_labels", Path(__file__).resolve().parents[1] / "scripts" / "disclosure_labels.py")
dl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dl)

# part, flag, evidence_seen, weight, label: R = registered (4 incomplete, 2 complete), F = flagged census,
# W = screen census, U = 2 drawn of 10 (weight 5), C = 2 drawn of 4 (weight 2).
ROWS = [("R", 0, 0, None, 1), ("R", 0, 0, None, 0), ("R", 0, 0, None, 0), ("R", 0, 0, None, 0),
        ("R", 0, 1, None, 0), ("R", 0, 1, None, 0),
        ("F", 1, 0, 1, 1), ("F", 1, 0, 1, 0), ("F", 1, 1, 1, 1),
        ("W", 0, 0, 1, 1), ("W", 0, 0, 1, 0),
        ("U", 0, 0, 5, 1), ("U", 0, 0, 5, 0),
        ("C", 0, 0, 2, 0), ("C", 0, 0, 2, 0)]
IN_B = {0, 1, 4, 6, 9}  # labeler B's overlap: three registered replies and two from the supplement


def _folder(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    pop = {"F": 3, "W": 2, "U": 10, "C": 4}
    key = pd.DataFrame([{"wid": f"A{i:03d}", "wid_B": f"B{i:03d}" if i in IN_B else None, "episode_id": f"e{i}",
                         "part": part, "population": pop.get(part), "sampled": {"U": 2, "C": 2}.get(part, pop.get(part)),
                         "weight": w, "model": "m1" if i % 2 else "m2", "answer_format": "final_line",
                         "evidence_seen": seen, "disclosure_flag": flag}
                        for i, (part, flag, seen, w, _) in enumerate(ROWS)])
    key.to_csv(tmp_path / "key.csv", index=False)
    for who, ids in (("A", key["wid"]), ("B", key["wid_B"].dropna())):
        (tmp_path / f"for-labeler-{who}").mkdir()
        pd.DataFrame({"wid": ids, "question": "How many?", "reply": "3"}).to_csv(
            tmp_path / f"for-labeler-{who}" / "worksheet.csv", index=False)
    (tmp_path / "inputs").mkdir()
    reg = key[key["part"] == "R"]
    reg[["episode_id"]].to_csv(tmp_path / "inputs" / "disclosure_to_label.csv", index=False)
    reg.loc[reg["wid_B"].notna(), ["episode_id"]].to_csv(tmp_path / "inputs" / "disclosure_to_label_second.csv", index=False)
    return tmp_path, key


def _labels(key: pd.DataFrame, flip_b: set[int] = frozenset()) -> tuple[pd.DataFrame, pd.DataFrame]:
    truth = [r[4] for r in ROWS]
    a = pd.DataFrame({"wid": key["wid"], "label": truth, "note": ""})
    b = pd.DataFrame({"wid": [f"B{i:03d}" for i in sorted(IN_B)],
                      "label": [1 - truth[i] if i in flip_b else truth[i] for i in sorted(IN_B)], "note": ""})
    return a, b


def _convert(d: Path, a: Path, b: Path, adjudicated: Path | None = None) -> None:
    argv = ["convert", "--dir", str(d), "--labels-a", str(a), "--labels-b", str(b), "--out-dir", str(d / "out")]
    dl.main([*argv, "--adjudicated", str(adjudicated)] if adjudicated else argv)


def test_read_labels_matches_by_name_and_reports_every_problem(tmp_path):
    ids = ["A001", "A002", "A003"]
    good = tmp_path / "good.csv"  # columns reordered, an extra column, 1.0 from a spreadsheet, a trailing blank row
    good.write_bytes("note,extra,label,WID\nsur\x8e,x,1.0,A001\n,,0,A002\n,,1, A003\n,,,\n".encode("latin-1"))
    df, problems, warnings = dl.read_labels(good, ids)
    assert not problems and list(df["label"]) == [1, 0, 1] and "Mac Roman" in warnings[0]
    assert df.loc[0, "note"] == "suré"  # 0x8E in Mac Roman
    bad = tmp_path / "bad.csv"
    bad.write_text("wid,label,note\nA001,2,\nA001,1,\nA009,0,\nA002,,\n")
    _, problems, _ = dl.read_labels(bad, ids)
    text = "\n".join(problems)
    for what in ["duplicated: A001", "not in the worksheet: A009", "missing: A003", "no label: A002", "A001='2'"]:
        assert what in text
    swapped = tmp_path / "swapped.csv"
    swapped.write_text("wid,label\nB001,0\n")
    assert "swapped" in dl.read_labels(swapped, ids, ["B001"])[1][0]


def test_convert_writes_the_registered_format_and_the_supplement(tmp_path):
    d, key = _folder(tmp_path)
    a, b = _labels(key)
    a.to_csv(d / "a.csv", index=False)
    b.to_csv(d / "b.csv", index=False)
    _convert(d, d / "a.csv", d / "b.csv")
    la, lb = pd.read_csv(d / "out" / "labels_a.csv"), pd.read_csv(d / "out" / "labels_b.csv")
    assert list(la.columns) == ["episode_id", "label"] and set(la["episode_id"]) == {f"e{i}" for i in range(6)}
    assert set(lb["episode_id"]) == {"e0", "e1", "e4"} and list(la["label"]) == [1, 0, 0, 0, 0, 0]
    sup = pd.read_csv(d / "out" / "supplement_labels.csv")
    assert len(sup) == 9 and set(sup["part"]) == {"F", "W", "U", "C"} and sup["label"].notna().all()
    assert len(pd.read_csv(d / "out" / "to_adjudicate.csv")) == 0


def test_convert_refuses_bad_files_and_writes_nothing(tmp_path):
    d, key = _folder(tmp_path)
    a, b = _labels(key)
    a.iloc[:-1].to_csv(d / "a.csv", index=False)  # one id missing
    b.to_csv(d / "b.csv", index=False)
    with pytest.raises(SystemExit, match="missing: A014"):
        _convert(d, d / "a.csv", d / "b.csv")
    assert not (d / "out").exists()
    a.to_csv(d / "a.csv", index=False)
    with pytest.raises(SystemExit, match="swapped"):
        _convert(d, d / "b.csv", d / "a.csv")


def test_disagreements_go_to_adjudication_and_block_the_estimate_until_settled(tmp_path):
    d, key = _folder(tmp_path)
    a, b = _labels(key, flip_b={1, 9})  # one registered and one supplement disagreement
    a.to_csv(d / "a.csv", index=False)
    b.to_csv(d / "b.csv", index=False)
    _convert(d, d / "a.csv", d / "b.csv")
    todo = pd.read_csv(d / "out" / "to_adjudicate.csv")
    assert set(todo["episode_id"]) == {"e1", "e9"} and "disclosure_flag" not in todo and "part" not in todo
    # the registered check's consensus, as `fplp disclosure check` would write it before adjudication
    cons = pd.DataFrame({"episode_id": [f"e{i}" for i in range(6)], "label_a": [1, 0, 0, 0, 0, 0],
                         "label_b": [1, 1, None, None, 0, None], "label": [1, None, 0, 0, 0, 0]})
    cons.to_csv(d / "cons.csv", index=False)
    with pytest.raises(SystemExit, match="not yet adjudicated"):
        dl.main(["estimate", "--dir", str(d), "--returned", str(d / "out"), "--consensus", str(d / "cons.csv")])
    pd.DataFrame({"episode_id": ["e1", "e9"], "label": [0, 1]}).to_csv(d / "adj.csv", index=False)
    _convert(d, d / "a.csv", d / "b.csv", d / "adj.csv")
    assert pd.read_csv(d / "out" / "supplement_labels.csv").set_index("episode_id").loc["e9", "label"] == 1
    pd.DataFrame({"episode_id": ["e5"], "label": [0]}).to_csv(d / "stray.csv", index=False)
    with pytest.raises(SystemExit, match="not disagreements"):
        _convert(d, d / "a.csv", d / "b.csv", d / "stray.csv")


def test_estimate_weights_missed_disclosures_and_reads_precision_on_the_census(tmp_path):
    d, key = _folder(tmp_path)
    a, b = _labels(key)
    a.to_csv(d / "a.csv", index=False)
    b.to_csv(d / "b.csv", index=False)
    _convert(d, d / "a.csv", d / "b.csv")
    pd.read_csv(d / "out" / "labels_a.csv").assign(label_a=lambda x: x["label"], label_b=None).to_csv(
        d / "cons.csv", index=False)
    out = d / "est.csv"
    dl.main(["estimate", "--dir", str(d), "--returned", str(d / "out"), "--consensus", str(d / "cons.csv"),
             "--out", str(out), "--n-boot", "500"])
    res = pd.read_csv(out)
    prec = res[res["quantity"] == "precision"].set_index("scope")
    assert prec.loc["every flagged reply", "value"] == pytest.approx(2 / 3)
    assert prec.loc["flagged incomplete answers", "value"] == pytest.approx(1 / 2)
    rec = res[(res["quantity"] == "recall, incomplete answers") & (res["model"] == "all")].iloc[0]
    # true positives 1; missed: registered 1 + screen 1 + 5 x 1 (U) + 2 x 0 (C) = 7; recall 1/8
    assert rec["value"] == pytest.approx(1 / 8) and rec["lo"] <= 1 / 8 <= rec["hi"]
    total = res[(res["quantity"].str.startswith("disclosures")) & (res["model"] == "all")].iloc[0]
    assert total["value"] == pytest.approx(8) and total["scope"] == "of 22"  # 4 + 2 + 2 + 10 + 4 incomplete answers
    again = d / "again.csv"
    dl.main(["estimate", "--dir", str(d), "--returned", str(d / "out"), "--consensus", str(d / "cons.csv"),
             "--out", str(again), "--n-boot", "500"])
    pd.testing.assert_frame_equal(res, pd.read_csv(again))
