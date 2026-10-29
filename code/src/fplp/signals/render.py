"""Serialize one page of rows with a given completeness signal.

The rows are identical across signal forms; only the signal changes. Every JSON form uses
the same {"results": [...]} body, and placement decides whether the signal fields come
before or after it. docs/signal-taxonomy.md shows a literal example of each form.
"""

from __future__ import annotations

import json

from fplp.signals.formats import Placement, SignalForm


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def note(start: int, n_rows: int, total: int) -> str:
    if n_rows == 0:
        return f"No more results ({total} total)."
    return f"Showing results {start + 1}-{start + n_rows} of {total}."


def _signal_fields(
    form: SignalForm, *, has_next: bool, total: int, next_cursor: str, next_url: str, text: str
) -> dict:
    if form is SignalForm.NONE:
        return {}
    if form is SignalForm.HAS_MORE:
        return {"has_more": has_next}
    if form is SignalForm.NEXT_CURSOR:
        return {"next_cursor": next_cursor if has_next else None}
    if form is SignalForm.TOTAL_COUNT:
        return {"total_count": total}
    if form is SignalForm.TOTAL_MATCHES:
        return {"total_matches": total}
    if form is SignalForm.LINK_HEADER:
        return {"headers": {"Link": f'<{next_url}>; rel="next"'} if has_next else {}}
    if form is SignalForm.PAGE_INFO:
        return {"pageInfo": {"hasNextPage": has_next, "endCursor": next_cursor}}
    if form is SignalForm.NL_NOTE_JSON:
        return {"message": text}
    if form is SignalForm.CURSOR_PLUS_NOTE:
        # The same note as nl_note_json, with no added instruction, so the combination differs from
        # its parts only by having both.
        return {"next_cursor": next_cursor if has_next else None, "message": text}
    raise ValueError(f"no JSON signal fields for {form}")


def render_page(
    rows: list[dict],
    form: SignalForm,
    *,
    start: int,
    total: int,
    has_next: bool,
    next_cursor: str,
    next_url: str,
    placement: Placement = Placement.BOTTOM,
    extra: dict | None = None,
) -> str:
    """Render the tool result the model sees.

    `has_next` is what the signal claims, which the false-signal conflict sets against the
    truth. `next_cursor` is the token for the row after this page; it is registered with the
    server whether or not more rows exist, as GraphQL's endCursor is. `extra` adds fields next to
    the signal (the visible-conflict levels use it for the field that contradicts the signal).
    """
    top = placement is Placement.TOP
    text = note(start, len(rows), total)

    if form is SignalForm.NL_NOTE:
        body = _dump({"results": rows})
        return f"{text}\n{body}" if top else f"{body}\n{text}"

    if form is SignalForm.PLACEHOLDER_ROW:
        remaining = total - start - len(rows)
        out: list = list(rows)
        if remaining > 0:
            marker = f"[… {remaining} more not shown]"
            out = [marker, *out] if top else [*out, marker]
        return _dump({"results": out})

    signal = _signal_fields(
        form, has_next=has_next, total=total, next_cursor=next_cursor, next_url=next_url, text=text
    )
    signal = {**signal, **(extra or {})}
    obj = {**signal, "results": rows} if top else {"results": rows, **signal}
    return _dump(obj)
