"""Traceability: episode ids follow the model settings, records carry code versions, failed episodes
are retried a fixed number of times, and scoring keeps only planned, unique episodes. No network."""

import csv
import hashlib
import json

from fplp import cli
from fplp.conditions import build_conditions, episode_id
from fplp.run import MAX_ATTEMPTS

BASE = {"name": "m", "provider": "openai_compatible", "model_id": "x", "temperature": 0, "price_in": 1.0}


def setup(tmp_path, models=("{name: s, provider: scripted, policy: follow_all}",), items=4):
    (tmp_path / "models.yaml").write_text("models:\n" + "".join(f"  - {m}\n" for m in models))
    cfg = tmp_path / "run.yaml"
    cfg.write_text(f"name: run\nmodels: [s]\nsignal_forms: [none]\ntask_need: [needs_all]\nitems_per_cell: {items}\n")
    return cfg


def run(tmp_path, cfg):
    cli.main(["run", str(cfg), "--models-file", str(tmp_path / "models.yaml"), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env"), "--workers", "1"])


def test_ids_change_with_behavior_settings_only():
    c = build_conditions({"signal_forms": ["none"], "task_need": ["needs_all"], "items_per_cell": 1})[0]
    base = episode_id(BASE, c, 12)
    assert episode_id({**BASE, "price_in": 9.0, "max_rpm": 5, "replicates": 1}, c, 12) == base
    for changed in ({**BASE, "temperature": 1}, {**BASE, "extra_body": {"reasoning": {"effort": "high"}}},
                    {**BASE, "model_id": "y"}):
        assert episode_id(changed, c, 12) != base
    assert episode_id(BASE, c, 8) != base


def test_records_carry_provenance(tmp_path):
    run(tmp_path, setup(tmp_path))
    rec = json.loads((tmp_path / "raw" / "run" / "s.jsonl").read_text().splitlines()[0])
    assert {"harness_version", "git_sha", "git_dirty", "python", "openai_sdk", "anthropic_sdk"} <= set(rec["provenance"])
    assert rec["config_key"] and rec["attempt"] == 1 and rec["max_tool_calls"] == 12


def test_failed_episodes_stop_after_max_attempts(tmp_path, monkeypatch, capsys):
    def failing(client, spec, max_tool_calls):
        raise RuntimeError("provider error")

    monkeypatch.setattr("fplp.run.run_episode", failing)
    cfg = setup(tmp_path, items=2)
    for _ in range(MAX_ATTEMPTS + 1):
        run(tmp_path, cfg)
    errors = [json.loads(x) for x in (tmp_path / "raw" / "run" / "s.errors.jsonl").read_text().splitlines()]
    assert len(errors) == 2 * MAX_ATTEMPTS  # no fourth attempt
    assert sorted(e["attempt"] for e in errors) == sorted(list(range(1, MAX_ATTEMPTS + 1)) * 2)
    assert f"failed {MAX_ATTEMPTS} times; reported as missing" in capsys.readouterr().out


def score(tmp_path, *extra):
    out = tmp_path / "scored.csv"
    cli.main(["score", str(tmp_path / "raw" / "run"), "--out", str(out), *extra])
    with out.open() as fh:
        return list(csv.DictReader(fh))


def test_score_with_config_keeps_planned_unique_episodes(tmp_path, capsys):
    cfg = setup(tmp_path)
    run(tmp_path, cfg)
    log = tmp_path / "raw" / "run" / "s.jsonl"
    lines = log.read_text().splitlines()
    stray = json.loads(lines[0])
    stray["episode_id"] = "not-planned"
    log.write_text("\n".join([*lines, lines[0], json.dumps(stray)]) + "\n")

    assert len(score(tmp_path)) == 5  # without a config: duplicates dropped, unplanned kept
    rows = score(tmp_path, "--config", str(cfg), "--models-file", str(tmp_path / "models.yaml"))
    out = capsys.readouterr().out
    assert len(rows) == 4 and "duplicate" in out and "does not plan" in out
    assert "s: 4 of 4 planned episodes scored, 0 missing" in out
    assert {"evidence_seen", "truncated"} <= set(rows[0])


def test_score_reports_missing_and_mixed_versions(tmp_path, capsys):
    cfg = setup(tmp_path)
    run(tmp_path, cfg)
    log = tmp_path / "raw" / "run" / "s.jsonl"
    recs = [json.loads(x) for x in log.read_text().splitlines()]
    recs[0]["provenance"] = {**recs[0]["provenance"], "git_sha": "0" * 40, "git_dirty": True}
    log.write_text("".join(json.dumps(r) + "\n" for r in recs[:3]))
    score(tmp_path, "--config", str(cfg), "--models-file", str(tmp_path / "models.yaml"))
    out = capsys.readouterr().out
    assert "3 of 4 planned episodes scored, 1 missing" in out
    assert "2 code versions" in out and "uncommitted changes" in out


def test_score_drops_retired_task_types(tmp_path, capsys):
    run(tmp_path, setup(tmp_path))
    log = tmp_path / "raw" / "run" / "s.jsonl"
    recs = [json.loads(x) for x in log.read_text().splitlines()]
    recs[0]["condition"]["task_type"] = "sum_amount"  # replaced by oldest_date after the checks
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    assert len(score(tmp_path)) == 3 and "retired task types" in capsys.readouterr().out


def test_dirty_flag_looks_only_at_code_and_configs(monkeypatch):
    from fplp import provenance as prov

    seen = []

    def fake_git(*args):
        seen.append(args)
        return "" if args[0] == "status" else "abc123"

    monkeypatch.setattr(prov, "_git", fake_git)
    info = prov.provenance()
    status = next(a for a in seen if a[0] == "status")
    assert status[-len(prov.BEHAVIOR_PATHS):] == prov.BEHAVIOR_PATHS and "results" not in status
    assert info["git_dirty"] is False and info["git_sha"] == "abc123"


def test_score_warns_when_the_served_model_changes(tmp_path, capsys):
    run(tmp_path, setup(tmp_path))
    log = tmp_path / "raw" / "run" / "s.jsonl"
    recs = [json.loads(x) for x in log.read_text().splitlines()]
    for i, r in enumerate(recs):
        for t in r["turns"]:
            t["served_model"] = "model-2026-09-28" if i else "model-2026-10-15"
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    score(tmp_path)
    assert "served by 2 model versions" in capsys.readouterr().out


def test_score_warns_when_the_served_model_differs_from_the_snapshot(tmp_path, capsys):
    cfg = setup(tmp_path, models=("{name: s, provider: scripted, policy: follow_all, snapshot: model-2026-09-28}",))
    run(tmp_path, cfg)
    log = tmp_path / "raw" / "run" / "s.jsonl"
    recs = [json.loads(x) for x in log.read_text().splitlines()]
    for r in recs:
        for t in r["turns"]:
            t["served_model"] = "model-2026-10-15"
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    score(tmp_path, "--config", str(cfg), "--models-file", str(tmp_path / "models.yaml"))
    assert "not the recorded snapshot 'model-2026-09-28'" in capsys.readouterr().out


def test_stamp_records_the_commit_and_input_checksums(tmp_path, capsys):
    data = tmp_path / "scored.csv"
    data.write_text("a,b\n1,2\n")
    out = tmp_path / "results" / "x.provenance.json"
    cli.main(["stamp", str(out), str(data)])
    rec = json.loads(out.read_text())
    assert rec["inputs"] == {str(data): hashlib.sha256(b"a,b\n1,2\n").hexdigest()}
    assert {"git_sha", "git_dirty", "created_at", "python"} <= set(rec)
    assert f"wrote {out}" in capsys.readouterr().out
