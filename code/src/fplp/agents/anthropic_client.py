"""Models served through the Anthropic Messages API, with a manual tool loop.

Notes for the methods section:
- Some current models on this API reject non-default `temperature`, so it is sent only when configured.
- Some models cannot disable extended reasoning; its depth is set with `effort`, which should be
  fixed explicitly in configs/models.yaml rather than left at the model's default.
- Server-side refusal fallbacks are deliberately not enabled: a fallback would answer with a
  different model and contaminate per-model results. A refusal ends the episode and is logged.
- With `prompt_cache`, each request marks the end of the conversation so far for Anthropic's prompt
  cache, so the next turn rereads that prefix at the cache price instead of the full input price.
  The prompt the model sees is unchanged. The marker goes on the last two user messages of the
  request (the previous one is read back, the new one written), never more, and the stored history
  carries no markers. Prompts below the model's minimum cacheable length are simply not cached.
"""

from __future__ import annotations

import copy
import os

import anthropic

from fplp.agents.base import ModelClient, RateLimiter, Session, ToolCall, Turn


class AnthropicClient(ModelClient):
    def __init__(
        self,
        name: str,
        model_id: str,
        effort: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 16000,
        max_retries: int = 6,
        max_rpm: float | None = None,
        prompt_cache: bool = False,
    ):
        self.name = name
        self.prompt_cache = prompt_cache
        self.limiter = RateLimiter(max_rpm)
        self.model_id = model_id
        self.effort = effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        # The SDK retries 408/409/429/5xx and connection errors with backoff. The key is passed
        # explicitly so the SDK never falls back to a stored login on another account.
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"), max_retries=max_retries)

    def open(self, system: str, user: str, tools: list[dict], oracle=None) -> Session:
        return _AnthropicSession(self, system, user, tools)


CACHE_MARK = {"type": "ephemeral"}


def _with_cache_marks(messages: list[dict], last_n: int = 2) -> list[dict]:
    """A copy of the history with a cache marker on the last block of the last `last_n` user
    messages; the history itself is left unmarked, so markers never accumulate past the API's limit."""
    marked = list(messages)
    users = [i for i, m in enumerate(messages) if m["role"] == "user"][-last_n:]
    for i in users:
        content = messages[i]["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else copy.deepcopy(content)
        blocks[-1] = {**blocks[-1], "cache_control": dict(CACHE_MARK)}
        marked[i] = {**messages[i], "content": blocks}
    return marked


class _AnthropicSession(Session):
    def __init__(self, owner: AnthropicClient, system: str, user: str, tools: list[dict]):
        self.owner = owner
        self.system = system
        self.tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ]
        self.messages: list[dict] = [{"role": "user", "content": user}]

    def _create(self, tool_choice: dict | None = None) -> Turn:
        o = self.owner
        kwargs: dict = {
            "model": o.model_id,
            "max_tokens": o.max_tokens,
            "system": self.system,
            "tools": self.tools,
            "messages": _with_cache_marks(self.messages) if o.prompt_cache else self.messages,
        }
        if o.effort:
            kwargs["output_config"] = {"effort": o.effort}
        if o.temperature is not None:
            kwargs["temperature"] = o.temperature
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        o.limiter.wait()
        response = o.client.messages.create(**kwargs)
        if not response.content and not response.usage.output_tokens and response.stop_reason != "refusal":
            raise RuntimeError("empty response with 0 output tokens")  # a glitch: retried, not scored
        cache_write = getattr(response.usage, "cache_creation_input_tokens", None) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", None) or 0
        # Append the full content, not just text, so thinking blocks go back unchanged.
        self.messages.append({"role": "assistant", "content": response.content})
        return Turn(
            reasoning="".join(getattr(b, "thinking", "") or "" for b in response.content if b.type == "thinking"),
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=[
                ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"
            ],
            stop_reason=response.stop_reason,
            # input_tokens excludes cached tokens; tokens_in counts every input token processed.
            tokens_in=response.usage.input_tokens + cache_write + cache_read,
            tokens_out=response.usage.output_tokens,
            cache_write=cache_write,
            cache_read=cache_read,
            served_model=getattr(response, "model", None),
            response_id=getattr(response, "id", None),
        )

    @staticmethod
    def _results(results: list[tuple[ToolCall, str]]) -> list[dict]:
        return [{"type": "tool_result", "tool_use_id": tc.id, "content": out} for tc, out in results]

    def first(self) -> Turn:
        return self._create()

    def reply(self, results: list[tuple[ToolCall, str]]) -> Turn:
        # All results for one turn go in a single user message.
        self.messages.append({"role": "user", "content": self._results(results)})
        return self._create()

    def finalize(self, results: list[tuple[ToolCall, str]], notice: str) -> Turn:
        content = [*self._results(results), {"type": "text", "text": notice}]
        self.messages.append({"role": "user", "content": content})
        turn = self._create(tool_choice={"type": "none"})
        turn.final_tool_choice = "none"
        return turn
