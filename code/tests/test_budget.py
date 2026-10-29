"""The spending guard: estimates, refusal without a cap or confirmation, and the hard cap. No network."""

import json
from pathlib import Path

import pytest

from fplp import cli
from fplp.budget import DEFAULT_TOKENS, Budget, plan_model

PRICED = {"price_in": 1.0, "price_out": 2.0}  # USD per million tokens


def write(tmp_path, models, config_extra=""):
    (tmp_path / "models.yaml").write_text("models:\n" + "".join(f"  - {m}\n" for m in models))
    cfg = tmp_path / "run.yaml"
    cfg.write_text("name: run\nsignal_forms: [none]\ntask_need: [needs_all]\nitems_per_cell: 10\n" + config_extra)
    return cfg


def run(tmp_path, cfg, *extra):
    cli.main(["run", str(cfg), "--models-file", str(tmp_path / "models.yaml"), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env"), "--workers", "1", *extra])


def test_budget_reservations_respect_the_cap():
    b = Budget(cap=1.0)
    assert b.reserve(0.6) and not b.reserve(0.6)   # reservations count against the cap
    b.settle(0.6, 0.2)
    assert b.reserve(0.6) and b.spent == pytest.approx(0.2)
    assert Budget(cap=None).reserve(1e9)          # no cap for free runs


def test_plan_uses_logged_tokens_or_a_high_default(tmp_path):
    entry = {"name": "m", "provider": "openai_compatible", "model_id": "x", **PRICED}
    plan = plan_model(entry, 10, tmp_path)
    assert plan.paid and plan.per_episode == pytest.approx(DEFAULT_TOKENS[0] / 1e6 + DEFAULT_TOKENS[1] * 2 / 1e6)
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "m.jsonl").write_text(json.dumps({"tokens_in": 1000, "tokens_out": 100}) + "\n")
    assert plan_model(entry, 10, tmp_path).per_episode == pytest.approx(0.0012)
    assert not plan_model({"name": "s", "provider": "scripted"}, 10, tmp_path).paid


PAID = "{name: paid, provider: openai_compatible, model_id: x, base_url: 'http://127.0.0.1:9', price_in: 1.0, price_out: 2.0}"


def test_paid_run_refused_without_a_cap(tmp_path, capsys):
    cfg = write(tmp_path, [PAID])
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "paid")
    assert "Nothing was sent" in str(exc.value) and "--max-cost" in str(exc.value)
    assert "estimated spend" in capsys.readouterr().out
    assert not (tmp_path / "raw" / "run").exists()


def test_paid_run_refused_without_confirmation(tmp_path):
    cfg = write(tmp_path, [PAID])
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "paid", "--max-cost", "5")
    assert "Not confirmed" in str(exc.value)
    assert not (tmp_path / "raw" / "run").exists()


def test_paid_run_refused_without_prices(tmp_path):
    cfg = write(tmp_path, ["{name: unpriced, provider: openai_compatible, model_id: x}"])
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "unpriced", "--max-cost", "5", "--yes")
    assert "without prices" in str(exc.value)


def test_cap_stops_new_episodes(tmp_path, monkeypatch, capsys):
    def fake_episode(client, spec, max_tool_calls):
        return {"tokens_in": 10_000, "tokens_out": 1_000, "empty_reply": False}  # $0.012 each

    monkeypatch.setattr("fplp.run.run_episode", fake_episode)
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all, price_in: 1.0, price_out: 2.0}"])
    run(tmp_path, cfg, "--model", "s", "--max-cost", "0.1", "--yes")
    written = len((tmp_path / "raw" / "run" / "s.jsonl").read_text().splitlines())
    out = capsys.readouterr().out
    assert 0 < written < 10 and "STOPPED at the spending cap" in out
    ledger = [json.loads(line) for line in Path(tmp_path / "spend-ledger.jsonl").read_text().splitlines()]
    assert ledger[0]["episodes"] == written and ledger[0]["cost"] <= 0.1 and ledger[0]["cap"] == 0.1


def test_failures_are_charged_completed_turns_and_a_streak_stops_the_run(tmp_path, monkeypatch, capsys):
    def failing(client, spec, max_tool_calls):
        e = RuntimeError("provider error")
        e.partial_tokens = (1_000, 100)  # one turn completed before the failure: $0.0012
        raise e

    monkeypatch.setattr("fplp.run.run_episode", failing)
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all, price_in: 1.0, price_out: 2.0}"])
    cfg.write_text(cfg.read_text().replace("items_per_cell: 10", "items_per_cell: 30"))
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "s", "--max-cost", "5", "--yes")
    assert exc.value.code == 1
    errors = (tmp_path / "raw" / "run" / "s.errors.jsonl").read_text().splitlines()
    assert len(errors) == 10                       # ten failures in a row stop the run
    out = capsys.readouterr().out
    assert "STOPPED after 10 failures in a row" in out and "STOPPED at the spending cap" not in out
    ledger = [json.loads(x) for x in (tmp_path / "spend-ledger.jsonl").read_text().splitlines()]
    assert ledger[-1]["tokens_in"] == 10_000 and ledger[-1]["failure_streak"]   # partial turns are counted
    assert ledger[-1]["budget_spent"] == pytest.approx(0.012)                   # not 10 phantom reservations


@pytest.mark.parametrize("error", [
    "Error code: 400 - {'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low'}}",
    "Error code: 401 - invalid x-api-key",
])
def test_account_errors_stop_at_once_without_using_attempts(tmp_path, monkeypatch, capsys, error):
    from fplp.run import _attempts

    class AccountError(Exception):
        status_code = 401 if "401" in error else 400

    def failing(client, spec, max_tool_calls):
        raise AccountError(error)

    monkeypatch.setattr("fplp.run.run_episode", failing)
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all, price_in: 1.0, price_out: 2.0}"])
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "s", "--max-cost", "5", "--yes")
    assert exc.value.code == 1
    err_path = tmp_path / "raw" / "run" / "s.errors.jsonl"
    errors = [json.loads(x) for x in err_path.read_text().splitlines()]
    assert len(errors) == 1 and errors[0]["fatal"] and errors[0]["attempt"] is None   # one request, then stop
    assert not _attempts(err_path)                                                     # no attempt used
    assert "STOPPED: account error" in capsys.readouterr().out


def test_missing_api_key_stops_before_anything_is_sent(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = write(tmp_path, ["{name: c, provider: anthropic, model_id: x, price_in: 1.0, price_out: 2.0}"])
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "c", "--max-cost", "5", "--yes")
    assert "API key not set" in str(exc.value) and "ANTHROPIC_API_KEY" in str(exc.value)
    assert not (tmp_path / "raw" / "run" / "c.jsonl").exists()


def test_truncated_log_line_does_not_break_estimates_or_resume(tmp_path):
    from fplp.budget import mean_tokens

    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all}"])
    run(tmp_path, cfg, "--model", "s", "--max-episodes", "3")
    log = tmp_path / "raw" / "run" / "s.jsonl"
    log.write_text(log.read_text() + '{"episode_id": "cut", "tokens_in": 5')   # a hard kill mid-write
    assert mean_tokens("s", tmp_path / "raw")[2] == 3
    run(tmp_path, cfg, "--model", "s")
    lines = log.read_text().splitlines()
    assert len([x for x in lines if x.startswith('{"episode_id": "cut"')]) == 1
    assert sum(1 for x in lines if x.endswith("}")) == 10   # every new record starts on its own line


def test_free_runs_need_no_cap(tmp_path):
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all}"])
    run(tmp_path, cfg, "--model", "s")
    assert len((tmp_path / "raw" / "run" / "s.jsonl").read_text().splitlines()) == 10


def test_interrupt_cancels_queued_episodes_and_records_spend(tmp_path, monkeypatch, capsys):
    import time

    import fplp.run as run_module
    from fplp.episode import run_episode as real

    calls = []

    def slow(client, spec, max_tool_calls):
        calls.append(1)
        time.sleep(0.05)  # long enough that the third episode is still running at the interrupt
        return real(client, spec, max_tool_calls=max_tool_calls)

    real_as_completed = run_module.as_completed

    def ctrl_c_after_two(fs):  # Ctrl-C reaches the main thread while it waits for results
        it = real_as_completed(fs)
        yield next(it)
        yield next(it)
        raise KeyboardInterrupt

    monkeypatch.setattr("fplp.run.run_episode", slow)
    monkeypatch.setattr("fplp.run.as_completed", ctrl_c_after_two)
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all, price_in: 1.0, price_out: 2.0}"])
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "s", "--max-cost", "5", "--yes")
    assert exc.value.code == 130
    assert len(calls) == 3                                   # nothing started after the interrupt
    written = (tmp_path / "raw" / "run" / "s.jsonl").read_text().splitlines()
    assert len(written) == 3 and "INTERRUPTED" in capsys.readouterr().out   # the running one was kept
    ledger = [json.loads(x) for x in (tmp_path / "spend-ledger.jsonl").read_text().splitlines()]
    assert ledger[-1]["interrupted"] and ledger[-1]["episodes"] == 3 and ledger[-1]["skipped"] == 7


def test_truncated_error_line_does_not_stop_a_run(tmp_path):
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all}"])
    (tmp_path / "raw" / "run").mkdir(parents=True)
    (tmp_path / "raw" / "run" / "s.errors.jsonl").write_text('{"episode_id": "x"}\n{"episode_id": "y", "trace')
    run(tmp_path, cfg, "--model", "s")
    assert len((tmp_path / "raw" / "run" / "s.jsonl").read_text().splitlines()) == 10
    assert (tmp_path / "raw" / "run" / "s.errors.jsonl").read_text() == '{"episode_id": "x"}\n'


def test_cost_drift_stops_the_run(tmp_path, monkeypatch, capsys):
    def costly(client, spec, max_tool_calls):  # 3x the default estimate of $0.024
        return {"tokens_in": 60_000, "tokens_out": 6_000, "empty_reply": False, "turns": []}

    monkeypatch.setattr("fplp.run.run_episode", costly)
    cfg = write(tmp_path, ["{name: s, provider: scripted, policy: follow_all, price_in: 1.0, price_out: 2.0}"])
    cfg.write_text(cfg.read_text().replace("items_per_cell: 10", "items_per_cell: 40"))
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, cfg, "--model", "s", "--max-cost", "50", "--yes")
    assert exc.value.code == 1
    written = len((tmp_path / "raw" / "run" / "s.jsonl").read_text().splitlines())
    assert written == 20 and "more than 1.5x the" in capsys.readouterr().out
    ledger = [json.loads(x) for x in (tmp_path / "spend-ledger.jsonl").read_text().splitlines()]
    assert ledger[-1]["cost_drift"]


def test_estimate_uses_the_runs_own_episodes_once_there_are_enough(tmp_path):
    entry = {"name": "m", "provider": "openai_compatible", "model_id": "x", **PRICED}
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "m.jsonl").write_text(json.dumps({"tokens_in": 1000, "tokens_out": 100}) + "\n")
    (tmp_path / "run").mkdir()
    own = tmp_path / "run" / "m.jsonl"
    own.write_text((json.dumps({"tokens_in": 5000, "tokens_out": 500}) + "\n") * 9)
    assert "logged episodes" in plan_model(entry, 1, tmp_path, "run").basis       # 9 < 10: all logs
    own.write_text(own.read_text() * 2)
    plan = plan_model(entry, 1, tmp_path, "run")
    assert "this run" in plan.basis and plan.per_episode == pytest.approx(0.006)  # 18 own episodes only


CACHED = {"price_in": 2.0, "price_out": 10.0, "price_cache_write": 2.5, "price_cache_read": 0.2}


def test_cache_tokens_are_priced_separately():
    from fplp.cost import episode_cost, record_cost

    # 10,000 tokens in: 1,000 uncached, 2,000 written to the cache, 7,000 read from it; 100 out
    assert episode_cost(CACHED, 10_000, 100, 2_000, 7_000) == pytest.approx(0.002 + 0.005 + 0.0014 + 0.001)
    assert episode_cost(CACHED, 10_000, 100) == pytest.approx(0.021)            # nothing cached: full price
    # without cache prices, writes cost 1.25x and reads the full input price: never understated
    assert episode_cost({"price_in": 2.0, "price_out": 10.0}, 10_000, 100, 2_000, 7_000) == pytest.approx(0.022)
    assert record_cost(CACHED, {"tokens_in": 10_000, "tokens_out": 100}) == pytest.approx(0.021)  # older logs


SCRIPTED_CACHED = ("{name: s, provider: scripted, policy: follow_all, price_in: 2.0, price_out: 10.0, "
                   "price_cache_write: 2.5, price_cache_read: 0.2}")


def test_runs_charge_cached_tokens_at_cache_prices(tmp_path, monkeypatch):
    def cached_episode(client, spec, max_tool_calls):
        return {"tokens_in": 10_000, "tokens_out": 100, "cache_write": 2_000, "cache_read": 7_000, "empty_reply": False}

    monkeypatch.setattr("fplp.run.run_episode", cached_episode)
    cfg = write(tmp_path, [SCRIPTED_CACHED])
    run(tmp_path, cfg, "--model", "s", "--max-cost", "5", "--yes")
    ledger = [json.loads(x) for x in (tmp_path / "spend-ledger.jsonl").read_text().splitlines()]
    n = ledger[-1]["episodes"]
    assert n == 10 and ledger[-1]["cache_read"] == 70_000
    assert ledger[-1]["budget_spent"] == pytest.approx(n * 0.0094) and ledger[-1]["cost"] == pytest.approx(n * 0.0094)


def test_failed_episodes_charge_cached_turns_at_cache_prices(tmp_path, monkeypatch):
    def failing(client, spec, max_tool_calls):
        e = RuntimeError("provider error")
        e.partial_tokens = (10_000, 100, 2_000, 7_000)
        raise e

    monkeypatch.setattr("fplp.run.run_episode", failing)
    cfg = write(tmp_path, [SCRIPTED_CACHED])
    with pytest.raises(SystemExit):
        run(tmp_path, cfg, "--model", "s", "--max-cost", "5", "--yes")
    ledger = [json.loads(x) for x in (tmp_path / "spend-ledger.jsonl").read_text().splitlines()]
    assert ledger[-1]["budget_spent"] == pytest.approx(10 * 0.0094)   # ten failures in a row stop the run


def test_estimates_use_logged_cache_tokens(tmp_path):
    entry = {"name": "m", "provider": "anthropic", "model_id": "x", "prompt_cache": True, **CACHED}
    (tmp_path / "r").mkdir()
    log = tmp_path / "r" / "m.jsonl"
    log.write_text(json.dumps({"tokens_in": 10_000, "tokens_out": 100}) + "\n")
    plan = plan_model(entry, 1, tmp_path)
    assert plan.per_episode == pytest.approx(0.021) and "without caching: likely high" in plan.basis
    log.write_text(json.dumps({"tokens_in": 10_000, "tokens_out": 100, "cache_write": 2_000, "cache_read": 7_000}) + "\n")
    plan = plan_model(entry, 1, tmp_path)
    assert plan.per_episode == pytest.approx(0.0094) and "likely high" not in plan.basis


@pytest.mark.parametrize("entry, message", [
    ("{name: m, provider: openai_compatible, model_id: x, prompt_cache: true}", "anthropic provider only"),
    ("{name: m, provider: anthropic, model_id: x, prompt_cache: true, price_in: 2, price_out: 10}", "price_cache_write"),
])
def test_prompt_cache_settings_are_validated(tmp_path, entry, message):
    from fplp.config import ConfigError, load_models

    (tmp_path / "models.yaml").write_text(f"models:\n  - {entry}\n")
    with pytest.raises(ConfigError, match=message):
        load_models(tmp_path / "models.yaml")
    assert load_models("configs/models.yaml")["claude-sonnet-5-5"]["prompt_cache"] is True
