"""Models behind an OpenAI-compatible Chat Completions endpoint: vLLM-served open-weight
models and hosted providers that expose that interface.

vLLM must be started with tool calling enabled (`--enable-auto-tool-choice` and the
`--tool-call-parser` that matches the model family). Provider-specific request fields go in
`extra_body`, for example OpenRouter's `provider` routing (to pin one host, so results do not
depend on which host served a request) and `reasoning` effort.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

from fplp.agents.base import ModelClient, RateLimiter, Session, ToolCall, Turn


class OpenAICompatibleClient(ModelClient):
    def __init__(
        self,
        name: str,
        model_id: str,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
        max_retries: int = 6,
        extra_body: dict | None = None,
        max_rpm: float | None = None,
    ):
        self.name = name
        self.limiter = RateLimiter(max_rpm)
        self.model_id = model_id
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens
        self.extra_body = extra_body
        # tool_choice for the forced final answer; falls back to "auto" (with the cap notice) if the
        # host rejects "none", as every gpt-oss host on OpenRouter did in the capcheck run.
        self.final_tool_choice = "none"
        # vLLM accepts any key; "EMPTY" is its convention.
        self.client = OpenAI(
            base_url=base_url, api_key=os.environ.get(api_key_env) or "EMPTY", max_retries=max_retries
        )

    def open(self, system: str, user: str, tools: list[dict], oracle=None) -> Session:
        return _OpenAISession(self, system, user, tools)


class _OpenAISession(Session):
    def __init__(self, owner: OpenAICompatibleClient, system: str, user: str, tools: list[dict]):
        self.owner = owner
        self.tools = [{"type": "function", "function": t} for t in tools]
        self.messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def request_kwargs(self, tool_choice: str = "auto") -> dict:
        o = self.owner
        kwargs: dict = {
            "model": o.model_id,
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": tool_choice,
        }
        if o.temperature is not None:
            kwargs["temperature"] = o.temperature
        if o.seed is not None:
            kwargs["seed"] = o.seed
        if o.max_tokens is not None:
            kwargs["max_tokens"] = o.max_tokens
        if o.extra_body:
            kwargs["extra_body"] = o.extra_body
        return kwargs

    def _create(self, tool_choice: str = "auto") -> Turn:
        self.owner.limiter.wait()
        response = self.owner.client.chat.completions.create(**self.request_kwargs(tool_choice))
        choice = response.choices[0]
        if choice.finish_reason == "error":  # OpenRouter: the upstream provider failed mid-response
            raise RuntimeError(f"provider returned finish_reason=error (response {response.id})")
        message = choice.message
        self.messages.append(message.model_dump(exclude_none=True))
        calls = []
        for tc in message.tool_calls or []:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_unparsed": tc.function.arguments}
            calls.append(ToolCall(tc.id, tc.function.name, arguments))
        usage = response.usage
        extra = message.model_extra or {}
        reasoning = extra.get("reasoning") or extra.get("reasoning_content") or ""
        # One vocabulary across providers: a content filter or an explicit refusal is "refusal"
        # (an outcome, not a protocol failure); "length" (output cut at max_tokens) is kept and
        # flagged as truncation in the episode record.
        refused = choice.finish_reason == "content_filter" or bool(getattr(message, "refusal", None))
        if not message.content and not calls and not refused and usage and usage.completion_tokens == 0:
            # Nothing generated at all: a provider glitch, retried as a failed attempt rather than
            # recorded as the model's empty reply.
            raise RuntimeError(f"empty response with 0 completion tokens (response {response.id})")
        return Turn(
            reasoning=reasoning if isinstance(reasoning, str) else "",
            text=message.content or "",
            tool_calls=calls,
            stop_reason="refusal" if refused else choice.finish_reason,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            served_model=response.model,
            response_id=response.id,
            served_by=(response.model_extra or {}).get("provider"),  # OpenRouter: the host that served it
            system_fingerprint=response.system_fingerprint,
        )

    def _append_results(self, results: list[tuple[ToolCall, str]]) -> None:
        for tc, out in results:
            self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})

    def first(self) -> Turn:
        return self._create()

    def reply(self, results: list[tuple[ToolCall, str]]) -> Turn:
        self._append_results(results)
        return self._create()

    def finalize(self, results: list[tuple[ToolCall, str]], notice: str) -> Turn:
        self._append_results(results)
        self.messages.append({"role": "user", "content": notice})
        choice = self.owner.final_tool_choice
        try:
            turn = self._create(tool_choice=choice)
        except Exception as e:
            if choice != "none" or not _rejects_tool_choice(e):
                raise
            # A rejected request is not billed: retry with "auto". The notice still says no more
            # tool calls are possible, and the episode loop executes none.
            self.owner.final_tool_choice = choice = "auto"
            turn = self._create(tool_choice=choice)
        turn.final_tool_choice = choice
        return turn


def _rejects_tool_choice(exc: Exception) -> bool:
    """The host (or router) refused the request because of tool_choice "none"."""
    text = str(exc).lower()
    return getattr(exc, "status_code", None) in (400, 404) and ("tool compatibility" in text or "tool_choice" in text)
