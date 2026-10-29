"""Provider-neutral interface between the episode loop and a model.

Each provider keeps its own native message history inside a Session, so provider-specific
content (for example reasoning blocks) is passed back unchanged.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class RateLimiter:
    """Space requests evenly to stay under a requests-per-minute limit, across worker threads."""

    def __init__(self, per_minute: float | None):
        self.interval = 60.0 / per_minute if per_minute else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self.interval
        time.sleep(max(0.0, slot - now))


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    tokens_in: int = 0   # every input token processed, cached or not
    tokens_out: int = 0
    # Of tokens_in, those written to and read from the provider's prompt cache (priced differently).
    cache_write: int = 0
    cache_read: int = 0
    reasoning: str = ""  # reasoning text the provider returns, if any (for diagnosis only)
    # As reported by the API, for provenance: the model that served the request (a router may
    # resolve an alias), the response id, the host behind a router, and the backend fingerprint.
    served_model: str | None = None
    response_id: str | None = None
    served_by: str | None = None
    system_fingerprint: str | None = None
    # On the forced final answer at the tool-call cap: the tool_choice sent ("none", or "auto" where
    # the host cannot disable tools; a tool call in that turn is then not executed).
    final_tool_choice: str | None = None


class Session(ABC):
    @abstractmethod
    def first(self) -> Turn:
        """Send the opening user message."""

    @abstractmethod
    def reply(self, results: list[tuple[ToolCall, str]]) -> Turn:
        """Return one result per tool call from the previous turn."""

    @abstractmethod
    def finalize(self, results: list[tuple[ToolCall, str]], notice: str) -> Turn:
        """Return results plus a notice, with tool use disabled, to force a final answer."""


class ModelClient(ABC):
    name: str

    @abstractmethod
    def open(self, system: str, user: str, tools: list[dict], oracle=None) -> Session:
        """Start an episode. `oracle` is the EpisodeSpec; only the scripted test client reads it."""
