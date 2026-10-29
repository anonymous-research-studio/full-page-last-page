"""Every shipped config validates, and validation rejects typos."""

from pathlib import Path

import pytest

from fplp.conditions import build_conditions
from fplp.config import ConfigError, load_models, load_run_config, validate_run_config

ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIGS = sorted((ROOT / "configs" / "runs").glob("*.yaml"))


@pytest.mark.parametrize("path", RUN_CONFIGS, ids=lambda p: p.stem)
def test_run_configs_validate_and_build(path):
    cfg = load_run_config(path)
    cfg = {**cfg, "items_per_cell": cfg.get("items_per_cell") or 4}
    assert build_conditions(cfg)


@pytest.mark.parametrize("path", RUN_CONFIGS, ids=lambda p: p.stem)
def test_run_config_models_are_registered(path):
    registry = load_models(ROOT / "configs" / "models.yaml")
    assert set(load_run_config(path).get("models") or []) <= set(registry)


BASE = {"name": "t", "signal_forms": ["none"], "task_need": ["needs_all"], "items_per_cell": 2}


@pytest.mark.parametrize("bad", [
    {"signal_form": ["none"]},                                   # misspelled key
    {"signal_forms": ["implicit_full"]},                         # retired level
    {"extents": ["more_ful"]},
    {"arms": {"documentation": {"base_form": "none", "levels": ["documneted"]}}},
    {"arms": {"placment": {"base_form": "none", "levels": ["top"]}}},
])
def test_validation_rejects_typos(bad):
    with pytest.raises(ConfigError):
        validate_run_config({**BASE, **bad})


def test_items_required_to_run():
    with pytest.raises(ConfigError):
        validate_run_config({**BASE, "items_per_cell": None}, require_items=True)


def test_env_file_sets_missing_keys_only(tmp_path, monkeypatch):
    from fplp.config import load_env_file

    env = tmp_path / ".env"
    env.write_text("# keys\nFPLP_TEST_A=one\nexport FPLP_TEST_B='two'\nFPLP_TEST_C=\nFPLP_TEST_D=from-file\n")
    monkeypatch.delenv("FPLP_TEST_A", raising=False)
    monkeypatch.delenv("FPLP_TEST_B", raising=False)
    monkeypatch.setenv("FPLP_TEST_D", "already-set")
    assert load_env_file(env) == ["FPLP_TEST_A", "FPLP_TEST_B"]
    import os

    assert os.environ["FPLP_TEST_B"] == "two" and os.environ["FPLP_TEST_D"] == "already-set"
    assert load_env_file(tmp_path / "missing.env") == []


def test_openrouter_entry_builds_pinned_request(monkeypatch):
    from fplp.agents import make_client

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    entry = load_models(ROOT / "configs" / "models.yaml")["gpt-oss-120b"]
    session = make_client(entry).open("system", "user", [{"name": "t", "description": "d", "parameters": {}}])
    kwargs = session.request_kwargs()
    assert kwargs["model"] == "openai/gpt-oss-120b" and kwargs["temperature"] == 0 and kwargs["seed"] == 0
    assert kwargs["extra_body"]["provider"] == {
        "order": ["crusoe/bf16"], "allow_fallbacks": False, "require_parameters": True,
    }


def test_rate_limiter_spaces_requests():
    import time

    from fplp.agents.base import RateLimiter

    limiter = RateLimiter(per_minute=600)  # one request per 0.1 s
    start = time.monotonic()
    for _ in range(4):
        limiter.wait()
    assert time.monotonic() - start >= 0.29
    unlimited = RateLimiter(None)
    start = time.monotonic()
    unlimited.wait()
    assert time.monotonic() - start < 0.05


def test_conflict_answer_formats_are_validated():
    with pytest.raises(ConfigError):
        validate_run_config({**BASE, "arms": {"conflict": {"levels": ["false_end"], "answer_formats": ["complete"]}}})
