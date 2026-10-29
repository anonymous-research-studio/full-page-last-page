"""Factor levels for the completeness-signal manipulation."""

from enum import StrEnum


class SignalForm(StrEnum):
    NONE = "none"                          # rows only, no signal
    HAS_MORE = "has_more"                  # "has_more": true | false
    NEXT_CURSOR = "next_cursor"            # "next_cursor": "<opaque>" | null
    TOTAL_COUNT = "total_count"            # "total_count": M
    TOTAL_MATCHES = "total_matches"        # "total_matches": M (amendment 2: the same total, unambiguously named)
    LINK_HEADER = "link_header"            # Link: <...>; rel="next", serialized into the result
    PAGE_INFO = "page_info"                # Relay-style pageInfo {hasNextPage, endCursor}
    NL_NOTE = "nl_note"                    # "Showing results 1-20 of 87." as text after the JSON
    NL_NOTE_JSON = "nl_note_json"          # the same note as a "message" field inside the JSON
    PLACEHOLDER_ROW = "placeholder_row"    # "[... 67 more not shown]" as the last array element
    CURSOR_PLUS_NOTE = "cursor_plus_note"  # next_cursor plus the nl_note_json note


class Extent(StrEnum):
    """Whether page 1 is full, crossed with whether more rows exist. Signals stay truthful;
    the off-diagonal cells are where the row count and the signal point different ways."""

    MORE_FULL = "more_full"    # page 1 full, more rows exist (the core case)
    LAST_FULL = "last_full"    # exactly one full page, nothing more
    LAST_SHORT = "last_short"  # fewer rows than the limit, nothing more
    MORE_SHORT = "more_short"  # page 1 short although more exist (Slack, AIP-158, Graph allow this)


class Placement(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"


class Conflict(StrEnum):
    """A signal that is false, as from a buggy API (page 1 only; later pages are truthful).

    The four false-end levels say "done" in different forms while more rows exist, so trust can be
    compared across forms; false_more says "more" on a true last page, to test the other direction.
    The two visible-conflict levels (amendment 1, H6) pair a false end with a second field on the same
    page that contradicts it, so an agent that reads the whole response can see the error.
    """

    FALSE_END = "false_end"                # has_more: false, more rows exist
    FALSE_END_CURSOR = "false_end_cursor"  # next_cursor: null, more rows exist
    FALSE_TOTAL = "false_total"            # total_count equal to the rows shown, more rows exist
    FALSE_NOTE = "false_note"              # "Showing results 1-20 of 20.", more rows exist
    FALSE_MORE = "false_more"              # has_more: true on a true last page
    VISIBLE_TOTAL = "visible_conflict_total"  # has_more: false beside a total_count above the rows shown
    VISIBLE_NOTE = "visible_conflict_note"    # next_cursor: null beside "Showing results 1-20 of 87."
