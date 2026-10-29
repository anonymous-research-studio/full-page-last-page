"""Deterministic stand-ins for a model, for tests and smoke runs. No API calls.

Policies:
- follow_all: request pages until one comes back empty.
- never_follow: request page 1 only.
- follow_if_full: request the next page while the last one was full (the row-count heuristic).
- follow_signal: request the next page while the response's completeness signal says more exist.
- signal_else_full: follow the signal when the response has one, and the row count when it has none
  (the pattern the protocol checks showed: signals override the row count, even false ones).

Each answers with gold once it has seen every row and "unknown" otherwise, so correctness tracks
completion. follow_if_full and follow_signal agree whenever a full page means more rows; the
last_full and more_short extents are where they come apart.
"""

from __future__ import annotations

import json
import re

from fplp.agents.base import ModelClient, Session, ToolCall, Turn

POLICIES = ("follow_all", "never_follow", "follow_if_full", "follow_signal", "signal_else_full")
_NOTE = re.compile(r"Showing results (\d+)-(\d+) of (\d+)")


def _body(tool_output: str) -> dict:
    start, end = tool_output.find("{"), tool_output.rfind("}")
    if start < 0:
        return {}
    try:
        return json.loads(tool_output[start : end + 1])
    except json.JSONDecodeError:
        return {}


def count_rows(tool_output: str) -> int:
    """Count data rows in a rendered tool result, ignoring notes and placeholder strings."""
    return sum(isinstance(r, dict) for r in _body(tool_output).get("results", []))


def signals_more(tool_output: str, rows_seen: int) -> bool:
    """Whether any completeness signal in the output says more rows exist."""
    body = _body(tool_output)
    if body.get("has_more") or body.get("next_cursor") or body.get("headers", {}).get("Link"):
        return True
    if body.get("pageInfo", {}).get("hasNextPage"):
        return True
    if any(isinstance(r, str) for r in body.get("results", [])):
        return True
    for total in ("total_count", "total_matches"):
        if total in body and body[total] > rows_seen:
            return True
    m = _NOTE.search(tool_output)
    return bool(m and int(m.group(2)) < int(m.group(3)))


def has_signal(tool_output: str) -> bool:
    """Whether the output carries any completeness signal, true or terminal, beyond the bare rows."""
    body = _body(tool_output)
    return bool(set(body) - {"results"}) or any(isinstance(r, str) for r in body.get("results", [])) \
        or bool(_NOTE.search(tool_output))


def format_gold(gold) -> str:
    if gold.answer_type == "count":
        return str(gold.value)
    if gold.answer_type == "amount":
        return f"{gold.value:.2f}"
    if gold.answer_type == "id_set":
        return ", ".join(gold.value)
    if gold.answer_type == "sku_any":
        return gold.accepted[0]
    return str(gold.value)


class ScriptedClient(ModelClient):
    def __init__(self, name: str, policy: str = "follow_all"):
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")
        self.name = name
        self.policy = policy

    def open(self, system: str, user: str, tools: list[dict], oracle=None) -> Session:
        if oracle is None:
            raise ValueError("ScriptedClient needs the episode spec as oracle")
        return _ScriptedSession(self.policy, oracle)


class _ScriptedSession(Session):
    def __init__(self, policy: str, spec):
        self.policy = policy
        self.spec = spec
        self.page = 0
        self.rows_seen = 0

    def _next_page(self) -> Turn:
        self.page += 1
        args = dict(self.spec.target_args)
        if self.page > 1:
            args["page"] = self.page
        return Turn("", [ToolCall(f"call_{self.page}", self.spec.target_tool, args)], "tool_use")

    def _answer(self) -> Turn:
        seen_all = self.rows_seen >= len(self.spec.rows)
        answer = format_gold(self.spec.gold) if seen_all else "unknown"
        return Turn(f"FINAL ANSWER: {answer}", [], "end_turn")

    def first(self) -> Turn:
        return self._next_page()

    def reply(self, results: list[tuple[ToolCall, str]]) -> Turn:
        _, out = results[-1]
        n = count_rows(out)
        self.rows_seen += n
        more = {
            "follow_all": n > 0,
            "never_follow": False,
            "follow_if_full": n >= self.spec.condition.page_limit,
            "follow_signal": signals_more(out, self.rows_seen),
            "signal_else_full": signals_more(out, self.rows_seen) if has_signal(out)
            else n >= self.spec.condition.page_limit,
        }[self.policy]
        return self._next_page() if more else self._answer()

    def finalize(self, results: list[tuple[ToolCall, str]], notice: str) -> Turn:
        return self._answer()
