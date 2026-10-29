import json

from fplp.signals.formats import Placement, SignalForm
from fplp.signals.render import render_page

ROWS = [{"id": i} for i in range(20)]
KW = {
    "start": 0,
    "total": 87,
    "has_next": True,
    "next_cursor": "tok",
    "next_url": "https://api.example.com/v1/x?cursor=tok",
}
JSON_FORMS = [f for f in SignalForm if f not in (SignalForm.NL_NOTE, SignalForm.PLACEHOLDER_ROW)]


def test_json_forms_share_rows():
    for form in JSON_FORMS:
        assert json.loads(render_page(ROWS, form, **KW))["results"] == ROWS


def test_signal_fields():
    assert json.loads(render_page(ROWS, SignalForm.HAS_MORE, **KW))["has_more"] is True
    assert json.loads(render_page(ROWS, SignalForm.NEXT_CURSOR, **KW))["next_cursor"] == "tok"
    assert json.loads(render_page(ROWS, SignalForm.TOTAL_COUNT, **KW))["total_count"] == 87
    assert 'rel="next"' in json.loads(render_page(ROWS, SignalForm.LINK_HEADER, **KW))["headers"]["Link"]
    assert json.loads(render_page(ROWS, SignalForm.PAGE_INFO, **KW))["pageInfo"] == {"hasNextPage": True, "endCursor": "tok"}
    assert json.loads(render_page(ROWS, SignalForm.NL_NOTE_JSON, **KW))["message"] == "Showing results 1-20 of 87."
    combined = json.loads(render_page(ROWS, SignalForm.CURSOR_PLUS_NOTE, **KW))
    assert combined == {"results": ROWS, "next_cursor": "tok", "message": "Showing results 1-20 of 87."}
    assert set(json.loads(render_page(ROWS, SignalForm.NONE, **KW))) == {"results"}


def test_full_last_page_signals():
    kw = {**KW, "total": 20, "has_next": False}
    assert json.loads(render_page(ROWS, SignalForm.HAS_MORE, **kw))["has_more"] is False
    assert json.loads(render_page(ROWS, SignalForm.NEXT_CURSOR, **kw))["next_cursor"] is None
    assert json.loads(render_page(ROWS, SignalForm.LINK_HEADER, **kw))["headers"] == {}
    assert json.loads(render_page(ROWS, SignalForm.TOTAL_COUNT, **kw))["total_count"] == 20
    assert json.loads(render_page(ROWS, SignalForm.NL_NOTE_JSON, **kw))["message"] == "Showing results 1-20 of 20."
    assert json.loads(render_page(ROWS, SignalForm.CURSOR_PLUS_NOTE, **kw))["next_cursor"] is None
    assert json.loads(render_page(ROWS, SignalForm.PLACEHOLDER_ROW, **kw))["results"] == ROWS


def test_nl_note_and_placement():
    bottom = render_page(ROWS, SignalForm.NL_NOTE, **KW)
    top = render_page(ROWS, SignalForm.NL_NOTE, **KW, placement=Placement.TOP)
    assert bottom.endswith("Showing results 1-20 of 87.")
    assert top.startswith("Showing results 1-20 of 87.")
    assert list(json.loads(render_page(ROWS, SignalForm.HAS_MORE, **KW, placement=Placement.TOP))) == ["has_more", "results"]


def test_placeholder_row():
    results = json.loads(render_page(ROWS, SignalForm.PLACEHOLDER_ROW, **KW))["results"]
    assert results[-1] == "[… 67 more not shown]" and results[:-1] == ROWS
