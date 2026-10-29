"""Load and validate run configs (configs/runs/*.yaml) and the model registry (configs/models.yaml).

Validation is strict: an unknown key or a misspelled level is an error, not a silent default,
because a typo in a run config would otherwise change the experiment without notice.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from fplp.conditions import ANSWER_FORMATS, DOC_WORDINGS, PHRASINGS, TASK_NEED, TaskNeed
from fplp.signals.formats import Conflict, Extent, Placement, SignalForm

RUN_KEYS = {
    "name", "models", "signal_forms", "extents", "task_need", "task_types", "other_extent_task_need",
    "items_per_cell", "page_limit", "max_tool_calls", "default_placement", "replicates", "seed", "arms",
    "retest_fraction",
}
REQUIRED_RUN_KEYS = {"name", "signal_forms", "task_need"}
ARM_KEYS = {"base_form", "base_forms", "levels", "task_need", "extents", "answer_formats"}
ARM_LEVELS = {
    "placement": {p.value for p in Placement},
    "documentation": {"documented", "undocumented"},
    "doc_wording": set(DOC_WORDINGS),
    "limit": {"stated", "unstated"},
    "phrasing": set(PHRASINGS),
    "answer_format": set(ANSWER_FORMATS),
    "extent": {e.value for e in Extent},
    "conflict": {c.value for c in Conflict},
    # A second false-signal arm, so the visible conflicts (H6) can run in fewer answer formats than
    # the false ends; its conditions belong to the "conflict" arm in the analysis.
    "visible_conflict": {c.value for c in Conflict},
}
MODEL_KEYS = {
    "name", "provider", "family", "model_id", "base_url", "api_key_env", "temperature", "seed",
    "effort", "max_tokens", "max_retries", "policy", "snapshot", "extra_body", "replicates", "max_rpm", "price_in", "price_out",
    "prompt_cache", "price_cache_write", "price_cache_read",
}
PROVIDERS = {"anthropic", "openai_compatible", "scripted"}


class ConfigError(ValueError):
    pass


def _check_values(where: str, values, allowed: set[str]) -> None:
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ConfigError(f"{where}: unknown value(s) {bad}; allowed: {sorted(allowed)}")


def validate_run_config(cfg: dict, *, require_items: bool = False) -> dict:
    if not isinstance(cfg, dict):
        raise ConfigError("run config must be a mapping")
    if unknown := set(cfg) - RUN_KEYS:
        raise ConfigError(f"unknown key(s) {sorted(unknown)}; allowed: {sorted(RUN_KEYS)}")
    if missing := REQUIRED_RUN_KEYS - set(cfg):
        raise ConfigError(f"missing key(s) {sorted(missing)}")
    if not 0 <= cfg.get("retest_fraction", 0) <= 1:
        raise ConfigError("retest_fraction must be between 0 and 1")
    if require_items and not cfg.get("items_per_cell"):
        raise ConfigError("items_per_cell must be set to run this config")

    forms, extents, needs = {f.value for f in SignalForm}, {e.value for e in Extent}, {n.value for n in TaskNeed}
    _check_values("signal_forms", cfg["signal_forms"], forms)
    _check_values("extents", cfg.get("extents", []), extents)
    _check_values("task_need", cfg["task_need"], needs)
    _check_values("other_extent_task_need", cfg.get("other_extent_task_need", []), needs)
    _check_values("task_types", cfg.get("task_types") or [], set(TASK_NEED))
    _check_values("default_placement", [cfg.get("default_placement", "bottom")], {p.value for p in Placement})

    for name, arm in (cfg.get("arms") or {}).items():
        if name not in ARM_LEVELS:
            raise ConfigError(f"arms: unknown arm {name!r}; allowed: {sorted(ARM_LEVELS)}")
        if not arm:
            continue
        if unknown := set(arm) - ARM_KEYS:
            raise ConfigError(f"arms.{name}: unknown key(s) {sorted(unknown)}; allowed: {sorted(ARM_KEYS)}")
        _check_values(f"arms.{name}.levels", arm.get("levels", []), ARM_LEVELS[name])
        base = arm.get("base_forms") or ([arm["base_form"]] if arm.get("base_form") else [])
        _check_values(f"arms.{name}.base_form(s)", base, forms)
        _check_values(f"arms.{name}.task_need", arm.get("task_need", []), needs)
        _check_values(f"arms.{name}.extents", arm.get("extents", []), extents)
        _check_values(f"arms.{name}.answer_formats", arm.get("answer_formats", []), set(ANSWER_FORMATS))
    return cfg


def load_run_config(path: str | Path, *, require_items: bool = False) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    try:
        return validate_run_config(cfg, require_items=require_items)
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from None


def load_models(path: str | Path) -> dict[str, dict]:
    """Return the model registry keyed by name, validating each entry."""
    entries = (yaml.safe_load(Path(path).read_text()) or {}).get("models") or []
    models: dict[str, dict] = {}
    for m in entries:
        if unknown := set(m) - MODEL_KEYS:
            raise ConfigError(f"{path}: model {m.get('name')!r}: unknown key(s) {sorted(unknown)}")
        if m.get("provider") not in PROVIDERS:
            raise ConfigError(f"{path}: model {m.get('name')!r}: provider must be one of {sorted(PROVIDERS)}")
        if m["provider"] != "scripted" and not m.get("model_id"):
            raise ConfigError(f"{path}: model {m['name']!r}: model_id is required")
        if m.get("prompt_cache") and m["provider"] != "anthropic":
            raise ConfigError(f"{path}: model {m['name']!r}: prompt_cache is implemented for the anthropic provider only")
        if m.get("prompt_cache") and m.get("price_in") is not None and (
                m.get("price_cache_write") is None or m.get("price_cache_read") is None):
            raise ConfigError(f"{path}: model {m['name']!r}: prompt_cache needs price_cache_write and price_cache_read")
        if m["name"] in models:
            raise ConfigError(f"{path}: duplicate model name {m['name']!r}")
        models[m["name"]] = m
    return models


def load_env_file(path: str | Path = ".env") -> list[str]:
    """Set KEY=VALUE pairs from a .env file into os.environ, without overriding variables that
    are already set. Returns the keys it set. Blank lines and # comments are skipped."""
    path = Path(path)
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
