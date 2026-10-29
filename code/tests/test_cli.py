"""The `fplp` command dispatches to every subcommand and runs the pipeline on scripted models."""

from pathlib import Path

import pytest

from fplp import cli

ROOT = Path(__file__).resolve().parents[1]


def test_help_lists_commands(capsys):
    cli.main([])
    out = capsys.readouterr().out
    assert all(name in out for name in cli.COMMANDS)


def test_unknown_command_exits_2():
    with pytest.raises(SystemExit) as exc:
        cli.main(["bogus"])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", list(cli.COMMANDS))
def test_every_command_has_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--help"])
    assert exc.value.code == 0
    assert f"fplp {command}" in capsys.readouterr().out


def test_run_score_show(tmp_path, capsys):
    raw = tmp_path / "raw"
    cli.main(["run", str(ROOT / "configs/runs/smoke.yaml"), "--models-file", str(ROOT / "configs/models.yaml"),
              "--model", "scripted-signal", "--max-episodes", "5", "--out-dir", str(raw)])
    log = raw / "smoke" / "scripted-signal.jsonl"
    assert len(log.read_text().splitlines()) == 5
    cli.main(["run", str(ROOT / "configs/runs/smoke.yaml"), "--models-file", str(ROOT / "configs/models.yaml"),
              "--model", "scripted-signal", "--max-episodes", "5", "--out-dir", str(raw)])
    assert len(log.read_text().splitlines()) == 10  # resumes: five new episodes, none repeated
    cli.main(["score", str(raw / "smoke"), "--out", str(tmp_path / "scored.csv")])
    cli.main(["show", str(log), "--n", "1"])
    assert "FINAL ANSWER" in capsys.readouterr().out


def test_model_replicate_cap(tmp_path):
    models = tmp_path / "models.yaml"
    models.write_text("models:\n  - {name: s3, provider: scripted, policy: follow_all}\n"
                      "  - {name: s1, provider: scripted, policy: follow_all, replicates: 1}\n")
    cfg = tmp_path / "rep.yaml"
    cfg.write_text("name: rep\nmodels: [s3, s1]\nsignal_forms: [none]\ntask_need: [needs_all]\n"
                   "items_per_cell: 2\nreplicates: 3\n")
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env")])
    count = {m: len((tmp_path / "raw" / "rep" / f"{m}.jsonl").read_text().splitlines()) for m in ("s3", "s1")}
    assert count == {"s3": 6, "s1": 2}


def test_cost_and_error_cleanup(tmp_path, capsys):
    from fplp.run import _drop_resolved_errors

    err = tmp_path / "m.errors.jsonl"
    err.write_text('{"episode_id": "a"}\n{"episode_id": "b"}\n')
    _drop_resolved_errors(err, {"a"})
    assert err.read_text() == '{"episode_id": "b"}\n'
    _drop_resolved_errors(err, {"a", "b"})
    assert not err.exists()

    models = tmp_path / "models.yaml"
    models.write_text("models:\n  - {name: s, provider: scripted, policy: follow_all, price_in: 1.0, price_out: 2.0}\n")
    log = tmp_path / "s.jsonl"
    log.write_text('{"model": "s", "tokens_in": 1000000, "tokens_out": 500000}\n')
    cli.main(["cost", str(log), "--models-file", str(models)])
    assert "2.00" in capsys.readouterr().out


def test_resume_ignores_a_truncated_last_line(tmp_path):
    from fplp.run import _done_ids

    log = tmp_path / "m.jsonl"
    log.write_text('{"episode_id": "a"}\n{"episode_id": "b"}\n{"episode_id": "c", "turns": [')
    assert _done_ids(log) == {"a", "b"}


def test_capcheck_config_forces_the_final_answer_at_the_cap(tmp_path):
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cfg = (root / "configs" / "runs" / "capcheck.yaml").read_text().replace(
        "models: [gpt-oss-120b, claude-sonnet-5-5, nemotron-3-super]", "models: [scripted-follow]")
    (tmp_path / "capcheck.yaml").write_text(cfg)
    cli.main(["run", str(tmp_path / "capcheck.yaml"), "--models-file", str(root / "configs" / "models.yaml"),
              "--out-dir", str(tmp_path / "raw"), "--env-file", str(tmp_path / "none.env")])
    recs = [json.loads(x) for x in (tmp_path / "raw" / "capcheck" / "scripted-follow.jsonl").read_text().splitlines()]
    assert len(recs) == 3 and all(r["hit_cap"] and r["final_text"] and r["max_tool_calls"] == 1 for r in recs)
