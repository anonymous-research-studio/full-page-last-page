"""Model clients and the provider-neutral session interface."""

from __future__ import annotations

from fplp.agents.base import ModelClient


def make_client(cfg: dict) -> ModelClient:
    """Build a client from one entry in configs/models.yaml. Provider SDKs import lazily."""
    provider = cfg["provider"]
    if provider == "anthropic":
        from fplp.agents.anthropic_client import AnthropicClient

        return AnthropicClient(
            name=cfg["name"],
            model_id=cfg["model_id"],
            effort=cfg.get("effort"),
            temperature=cfg.get("temperature"),
            max_tokens=cfg.get("max_tokens", 16000),
            max_retries=cfg.get("max_retries", 6),
            max_rpm=cfg.get("max_rpm"),
            prompt_cache=bool(cfg.get("prompt_cache", False)),
        )
    if provider == "openai_compatible":
        from fplp.agents.openai_client import OpenAICompatibleClient

        return OpenAICompatibleClient(
            name=cfg["name"],
            model_id=cfg["model_id"],
            base_url=cfg.get("base_url"),
            api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
            temperature=cfg.get("temperature"),
            seed=cfg.get("seed"),
            max_tokens=cfg.get("max_tokens"),
            max_retries=cfg.get("max_retries", 6),
            extra_body=cfg.get("extra_body"),
            max_rpm=cfg.get("max_rpm"),
        )
    if provider == "scripted":
        from fplp.agents.scripted import ScriptedClient

        return ScriptedClient(name=cfg["name"], policy=cfg.get("policy", "follow_all"))
    raise ValueError(f"unknown provider: {provider}")
