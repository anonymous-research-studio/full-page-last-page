"""The disclosure-validation worksheet builder (scripts/disclosure_worksheet.py)."""

import importlib.util
from pathlib import Path

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "disclosure_worksheet", Path(__file__).resolve().parents[1] / "scripts" / "disclosure_worksheet.py")
dw = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dw)


def _scored() -> pd.DataFrame:
    rows = [{"episode_id": f"e{i}", "model": "m", "task_need": "needs_all", "empty_reply": 0, "arm": "core",
             "answer_format": "completeness" if i % 4 == 0 else "final_line", "evidence_seen": int(i % 3 == 0),
             "disclosure_flag": int(i in (5, 7)), "stop_reason": "stop"} for i in range(60)]
    rows.append({**rows[1], "episode_id": "r1", "arm": "retest"})          # retests are left out
    rows.append({**rows[1], "episode_id": "p1", "task_need": "page1_sufficient"})
    return pd.DataFrame(rows)


def test_supplement_parts_weights_and_exclusions():
    scored = _scored()
    registered = {"e1", "e2"}
    screen = {"e4", "e8", "e10"}
    sup = dw.supplement(scored, registered, screen, n_u=5, n_c=3, seed=1)
    assert not set(sup["episode_id"]) & (registered | {"r1", "p1"})
    assert set(sup.loc[sup["part"] == "F", "episode_id"]) == {"e5", "e7"}
    w = sup[sup["part"] == "W"]
    assert set(w["episode_id"]) <= screen and (w["weight"] == 1).all()
    for part, n in (("U", 5), ("C", 3)):
        s = sup[sup["part"] == part]
        assert len(s) == n and (s["weight"] == s["population"] / n).all()
        assert (s["disclosure_flag"] == 0).all() and (s["evidence_seen"] == 0).all()
    again = dw.supplement(scored, registered, screen, n_u=5, n_c=3, seed=1)
    assert list(again["episode_id"]) == list(sup["episode_id"])


def test_worksheet_shows_only_id_question_reply_and_labels_are_kept(tmp_path):
    view = pd.DataFrame({"wid": ["A001"], "question": ["How many?"], "reply": ["FINAL ANSWER: 3 <b>"]})
    page = dw.worksheet_html(view, "t")
    assert "A001" in page and "&lt;b&gt;" in page and "disclosure_flag" not in page and "{{" not in page
    labels = tmp_path / "labels.csv"
    assert dw.write_blank(labels, ["A001"]).startswith("wrote")
    labels.write_text("wid,label,note\nA001,1,x\n")
    assert dw.write_blank(labels, ["A001"]).startswith("kept") and "A001,1,x" in labels.read_text()
