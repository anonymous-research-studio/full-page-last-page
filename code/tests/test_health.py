"""fplp health: a clean scripted run raises no flag, each mechanical problem flags its cell, failures
count until recovered, and no outcome rate is reported."""

import json
from pathlib import Path

import pytest

from fplp import cli
from fplp.health import PROBLEMS, health_table

CONFIG = """name: hc
models: [scripted-hybrid]
signal_forms: [none, has_more]
extents: [more_full, last_full]
task_need: [needs_all]
items_per_cell: 12
"""
WITH_FIELD = "arms:\n  answer_format: {base_forms: [none], levels: [final_line, completeness], task_need: [needs_all]}\n"
MODELS = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"


@pytest.fixture
def run_dir(tmp_path):
    cfg = tmp_path / "hc.yaml"
    cfg.write_text(CONFIG)
    cli.main(["run", str(cfg), "--models-file", str(MODELS), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env"), "--workers", "4"])
    return tmp_path / "raw" / "hc", cfg


def health(raw, cfg, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["health", str(raw), "--config", str(cfg), "--models-file", str(MODELS)])
    return exc.value.code, capsys.readouterr().out


def test_clean_run_flags_nothing_and_shows_no_outcomes(run_dir, capsys):
    raw, cfg = run_dir
    code, out = health(raw, cfg, capsys)
    assert code == 0 and "problems: none" in out and "cells flagged 0 of 4" in out
    for outcome in ("follow_up", "correct", "disclos", "fetch"):
        assert outcome not in out


def rewrite(log: Path, change) -> None:
    recs = [json.loads(line) for line in log.read_text().splitlines()]
    change(recs)
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))


@pytest.mark.parametrize("problem, change", [
    ("empty", lambda r: r.update(empty_reply=True)),
    ("refused", lambda r: r.update(stop_reason="refusal")),
    ("no_final", lambda r: r.update(final_text="I think it is 3.")),
])
def test_each_problem_flags_its_cell(run_dir, capsys, problem, change):
    raw, cfg = run_dir
    rewrite(raw / "scripted-hybrid.jsonl", lambda recs: change(recs[0]))
    code, out = health(raw, cfg, capsys)
    assert code == 1 and f"{problem} 1" in out and "cells flagged 1 of 4" in out


def test_missing_completeness_line_counts_only_where_asked(tmp_path):
    cfg = tmp_path / "hc.yaml"
    cfg.write_text(CONFIG + WITH_FIELD)
    cli.main(["run", str(cfg), "--models-file", str(MODELS), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env"), "--workers", "4"])
    raw = tmp_path / "raw" / "hc"
    rewrite(raw / "scripted-hybrid.jsonl", lambda recs: [r.update(final_text="FINAL ANSWER: 3") for r in recs])
    from fplp.config import load_models
    from fplp.health import _plan_cells

    table = health_table(raw, ["scripted-hybrid"], load_models(MODELS),
                         _plan_cells(str(cfg), str(MODELS), ["scripted-hybrid"]))
    asked = table[table["answer_format"] == "completeness"]
    assert (asked["no_completeness"] == asked["run"]).all() and asked["run"].sum() > 0
    assert table.loc[table["answer_format"] == "final_line", "no_completeness"].sum() == 0


def test_failures_count_until_recovered(run_dir, capsys):
    raw, cfg = run_dir
    recs = [json.loads(line) for line in (raw / "scripted-hybrid.jsonl").read_text().splitlines()]
    lost = recs.pop(0)
    (raw / "scripted-hybrid.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    (raw / "scripted-hybrid.errors.jsonl").write_text(json.dumps(
        {"episode_id": lost["episode_id"], "condition": lost["condition"], "error": "boom"}) + "\n")
    code, out = health(raw, cfg, capsys)
    assert code == 1 and "failed 1" in out and f"{len(recs)} episodes of {len(recs) + 1} planned" in out
    (raw / "scripted-hybrid.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [lost, *recs]))
    code, out = health(raw, cfg, capsys)          # a later attempt succeeded: no longer a failure
    assert code == 0 and "failed" not in out.split("problems:")[1].split(";")[0]


def test_tool_errors_flag_only_above_ten_percent(run_dir):
    raw, _ = run_dir
    from fplp.config import load_models

    def errors(n):
        def change(recs):
            cell = [r for r in recs if r["condition"]["signal_form"] == "has_more" and r["condition"]["extent"] == "more_full"]
            for r in cell[:n]:
                r["calls"][0]["error"] = "invalid cursor"
        return change

    def row():
        table = health_table(raw, ["scripted-hybrid"], load_models(MODELS))
        return table[(table.signal_form == "has_more") & (table.extent == "more_full")].iloc[0]

    rewrite(raw / "scripted-hybrid.jsonl", errors(1))
    assert row()["tool_error"] == 1 and not row()["flagged"]      # 1 of 12 episodes: reported, not flagged
    rewrite(raw / "scripted-hybrid.jsonl", errors(2))
    assert row()["tool_error"] == 2 and row()["flagged"]          # 2 of 12 is above 10%
    assert all(row()[p] == 0 for p in PROBLEMS)


def test_live_episode_checks_usage_model_and_host():
    from fplp.health import episode_health

    rec = {"condition": {"arm": "core", "signal_form": "none", "extent": "more_full", "task_need": "needs_all",
                         "answer_format": "final_line", "documented": True},
           "final_text": "FINAL ANSWER: 3", "calls": [],
           "turns": [{"tokens_in": 0, "tokens_out": 0, "served_model": "other", "served_by": "SomeHost"}]}
    h = episode_health(rec, snapshot="expected", host="crusoe")
    assert (h["no_usage"], h["wrong_model"], h["wrong_host"]) == (1, 1, 1)
    assert episode_health(rec, live=False)["no_usage"] == 0      # scripted models report no usage
    rec["turns"][0].update(tokens_in=10, served_model="expected", served_by="Crusoe")
    h = episode_health(rec, snapshot="expected", host="crusoe")
    assert (h["no_usage"], h["wrong_model"], h["wrong_host"]) == (0, 0, 0)
