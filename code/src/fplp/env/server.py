"""Mock paginated API. Serves one episode's controlled result set and logs every call.

A list call "hits the target" when its query matches the episode's target query; only then
does it return the controlled rows. Any other query returns an empty result set, so the
agent's only source of answer-bearing rows is the manipulated one.
"""

from __future__ import annotations

import base64
import hashlib
import json
from urllib.parse import urlencode

from fplp.env.tools import QUERY_ARG, RESOURCE_PATHS, TOOL_NAMES
from fplp.signals.formats import Conflict, Extent
from fplp.signals.render import note, render_page
from fplp.tasks.specs import EpisodeSpec

API_BASE = "https://api.example.com/v1"


class ToolError(Exception):
    pass


def _norm(value) -> str:
    return " ".join(str(value).lower().split())


def _query_terms(value) -> set[str]:
    return {w.rstrip("s") for w in _norm(value).replace(",", " ").split()}


def _int_arg(args: dict, key: str, default: int | None) -> int | None:
    if args.get(key) in (None, ""):
        return default
    try:
        return int(args[key])
    except (TypeError, ValueError, OverflowError):  # OverflowError: JSON Infinity
        raise ToolError(f"{key} must be an integer") from None


def _asks_past_page_one(args: dict) -> bool:
    """A paging attempt, judged from the raw arguments so it counts even if they are invalid."""
    if args.get("cursor"):
        return True
    try:
        return float(args.get("page") or 1) > 1
    except (TypeError, ValueError, OverflowError):
        return False


class MockAPI:
    def __init__(self, spec: EpisodeSpec):
        self.spec = spec
        self.condition = spec.condition
        self.max_limit = spec.condition.page_limit
        self.calls: list[dict] = []
        self._cursor_offsets: dict[str, tuple[str, str, int]] = {}

    def call(self, name: str, arguments: dict) -> str:
        args = arguments if isinstance(arguments, dict) else {}
        record = {
            "tool": name,
            "arguments": args,
            "is_target": False,
            "paging": False,  # the call asked for something other than the first page
            "offset": None,
            "limit": None,
            "n_rows": 0,
            "error": None,
            "output": "",
        }
        self.calls.append(record)
        try:
            out = self._dispatch(name, args, record)
        except ToolError as e:
            record["error"] = str(e)
            out = json.dumps({"error": str(e)})
        record["output"] = out
        return out

    def _dispatch(self, name: str, args: dict, record: dict) -> str:
        if name not in TOOL_NAMES:
            raise ToolError(f"unknown tool: {name}")
        if name == "get_ticket":
            return self._get_ticket(args)
        key = QUERY_ARG[name]
        if not args.get(key):
            raise ToolError(f"missing required argument: {key}")
        record["is_target"] = self._is_target(name, args)
        rows = self.spec.rows if record["is_target"] else []
        return self._page(name, args, rows, record)

    def _is_target(self, name: str, args: dict) -> bool:
        if name != self.spec.target_tool:
            return False
        key = QUERY_ARG[name]
        target = self.spec.target_args[key]
        if name == "search_products":
            # "lamps" and "cheap lamp" both reach the "lamp" result set.
            return _norm(target) in _query_terms(args[key])
        return _norm(args[key]) == _norm(target)

    def _page(self, name: str, args: dict, rows: list[dict], record: dict) -> str:
        record["paging"] = _asks_past_page_one(args)  # before parsing, which may reject the call
        limit = max(1, min(_int_arg(args, "limit", self.max_limit), self.max_limit))
        conflict = self.condition.conflict if record["is_target"] else None
        first_size = limit
        if record["is_target"] and self.condition.extent is Extent.MORE_SHORT:
            # Short relative to whatever limit was requested, so the extent holds for any limit.
            first_size = max(1, min(self.spec.short_first_page, limit - 1))

        cursor = args.get("cursor")
        page = _int_arg(args, "page", None)
        record["limit"] = limit
        if cursor:
            issued = self._cursor_offsets.get(str(cursor))
            if issued is None or issued[:2] != (name, _norm(args[QUERY_ARG[name]])):
                raise ToolError("invalid cursor")  # unknown, or issued for a different query
            offset = issued[2]
        elif page is not None:
            if page < 1:
                raise ToolError("page must be >= 1")
            offset = 0 if page == 1 else first_size + (page - 2) * limit
        else:
            offset = 0

        page_rows = rows[offset : offset + (first_size if offset == 0 else limit)]
        end = offset + len(page_rows)
        has_next, shown_total = end < len(rows), len(rows)
        extra = None
        if conflict is not None and offset == 0:
            if conflict in (Conflict.FALSE_END, Conflict.FALSE_END_CURSOR, Conflict.FALSE_NOTE,
                            Conflict.VISIBLE_TOTAL, Conflict.VISIBLE_NOTE):
                has_next = False
            # Visible conflicts: a second field on the same page tells the truth and contradicts the end.
            if conflict is Conflict.VISIBLE_TOTAL:
                extra = {"total_count": len(rows)}
            if conflict is Conflict.VISIBLE_NOTE:
                extra = {"message": note(offset, len(page_rows), len(rows))}
            if conflict in (Conflict.FALSE_TOTAL, Conflict.FALSE_NOTE):
                shown_total = end  # "of 20" while more rows exist
            if conflict is Conflict.FALSE_MORE:
                has_next = True    # "more" on a true last page; the next page is empty
        record.update(offset=offset, n_rows=len(page_rows))

        token = self._token(name, args, end)
        return render_page(
            page_rows,
            self.condition.signal_form,
            start=offset,
            total=shown_total,
            has_next=has_next,
            next_cursor=token,
            next_url=self._next_url(name, args, token, limit),
            placement=self.condition.placement,
            extra=extra,
        )

    def _token(self, name: str, args: dict, offset: int) -> str:
        """Opaque cursor; the server keeps the mapping, so it cannot be decoded or forged."""
        raw = f"{self.condition.seed}:{name}:{_norm(args[QUERY_ARG[name]])}:{offset}"
        token = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()[:15]).decode()
        self._cursor_offsets[token] = (name, _norm(args[QUERY_ARG[name]]), offset)
        return token

    def _next_url(self, name: str, args: dict, token: str, limit: int) -> str:
        key = QUERY_ARG[name]
        query = urlencode({key: args[key], "cursor": token, "limit": limit})
        return f"{API_BASE}/{RESOURCE_PATHS[name]}?{query}"

    def _get_ticket(self, args: dict) -> str:
        wanted = _norm(args.get("ticket_id", "")).upper()
        if self.spec.target_tool == "list_tickets":
            for row in self.spec.rows:
                if row["ticket_id"] == wanted:
                    detail = {**row, "description": f"Customer reports: {row['subject'].lower()}."}
                    return json.dumps({"ticket": detail})
        raise ToolError("ticket not found")
