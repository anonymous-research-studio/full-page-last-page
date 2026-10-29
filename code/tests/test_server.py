import json

import pytest

from fplp.env.server import MockAPI
from fplp.env.tools import tool_schemas
from fplp.signals.formats import Conflict, Extent, SignalForm
from fplp.tasks.specs import build_episode


def _api(make_condition, form="has_more", **kw):
    spec = build_episode(make_condition(form, "filtered_count", item=1, **kw))
    return spec, MockAPI(spec)


def _body(out):
    return json.loads(out[out.find("{") : out.rfind("}") + 1])


def test_page_and_cursor_walk_cover_all_rows(make_condition):
    spec, api = _api(make_condition, "next_cursor")
    seen, out = [], api.call(spec.target_tool, spec.target_args)
    while True:
        body = _body(out)
        seen += body["results"]
        if not body["next_cursor"]:
            break
        out = api.call(spec.target_tool, {**spec.target_args, "cursor": body["next_cursor"]})
    assert seen == spec.rows

    by_page, page = [], 1
    while rows := _body(api.call(spec.target_tool, {**spec.target_args, "page": page}))["results"]:
        by_page += rows
        page += 1
    assert by_page == spec.rows


def test_target_matching_is_forgiving_but_exact_on_names(make_condition):
    spec, api = _api(make_condition)
    customer = spec.target_args["customer"]
    assert _body(api.call("list_orders", {"customer": customer.upper()}))["results"]
    assert not _body(api.call("list_orders", {"customer": customer.split()[0]}))["results"]
    assert api.calls[0]["is_target"] and not api.calls[1]["is_target"]


def test_errors_are_logged(make_condition):
    spec, api = _api(make_condition)
    assert "invalid cursor" in api.call(spec.target_tool, {**spec.target_args, "cursor": "nope"})
    assert api.calls[-1]["paging"] and api.calls[-1]["error"]
    assert "unknown tool" in api.call("delete_orders", {})


def test_last_full_is_one_truthful_full_page(make_condition):
    spec, api = _api(make_condition, extent=Extent.LAST_FULL)
    body = _body(api.call(spec.target_tool, spec.target_args))
    assert len(body["results"]) == 20 and body["has_more"] is False
    assert _body(api.call(spec.target_tool, {**spec.target_args, "page": 2}))["results"] == []


def test_more_short_first_page_is_short_and_truthful(make_condition):
    spec, api = _api(make_condition, extent=Extent.MORE_SHORT)
    body = _body(api.call(spec.target_tool, spec.target_args))
    assert len(body["results"]) == spec.short_first_page < 20 and body["has_more"] is True
    page2 = _body(api.call(spec.target_tool, {**spec.target_args, "page": 2}))["results"]
    assert page2[0] == spec.rows[spec.short_first_page]


def test_false_end_conflict(make_condition):
    spec, api = _api(make_condition, conflict=Conflict.FALSE_END)
    body = _body(api.call(spec.target_tool, spec.target_args))
    assert len(body["results"]) == 20 and body["has_more"] is False and len(spec.rows) > 20


def test_limit_can_be_hidden():
    shown = tool_schemas(20, documented=True, limit_stated=True)[0]
    hidden = tool_schemas(20, documented=True, limit_stated=False)[0]
    assert "at most 20" in shown["description"] and "maximum" in shown["parameters"]["properties"]["limit"]
    assert "20" not in hidden["description"] and "maximum" not in hidden["parameters"]["properties"]["limit"]


@pytest.mark.parametrize(("conflict", "form_check"), [
    (Conflict.FALSE_END, lambda b: b["has_more"] is False),
    (Conflict.FALSE_END_CURSOR, lambda b: b["next_cursor"] is None),
    (Conflict.FALSE_TOTAL, lambda b: b["total_count"] == 20),
    (Conflict.FALSE_NOTE, lambda b: b["message"] == "Showing results 1-20 of 20."),
])
def test_false_end_signals_say_done_while_more_exist(conflict, form_check):
    from fplp.conditions import CONFLICT_BASE_FORM, Condition

    spec = build_episode(Condition(CONFLICT_BASE_FORM[conflict], "filtered_count", 1, conflict=conflict))
    api = MockAPI(spec)
    page1 = _body(api.call(spec.target_tool, spec.target_args))
    assert len(page1["results"]) == 20 and len(spec.rows) > 20 and form_check(page1)
    page2 = _body(api.call(spec.target_tool, {**spec.target_args, "page": 2}))
    assert page2["results"] == spec.rows[20:40]  # later pages are truthful


def test_false_more_says_more_on_a_true_last_page():
    from fplp.conditions import Condition

    spec = build_episode(Condition(SignalForm.HAS_MORE, "filtered_count", 1, extent=Extent.LAST_FULL,
                                   conflict=Conflict.FALSE_MORE))
    api = MockAPI(spec)
    assert _body(api.call(spec.target_tool, spec.target_args))["has_more"] is True and len(spec.rows) == 20
    assert _body(api.call(spec.target_tool, {**spec.target_args, "page": 2}))["results"] == []


def test_cursor_is_bound_to_its_query(make_condition):
    spec, api = _api(make_condition, "next_cursor")
    token = _body(api.call(spec.target_tool, spec.target_args))["next_cursor"]
    assert "invalid cursor" in api.call("list_orders", {"customer": "Someone Else", "cursor": token})
    assert "invalid cursor" in api.call("search_products", {"query": "lamp", "cursor": token})
    assert _body(api.call(spec.target_tool, {**spec.target_args, "cursor": token}))["results"] == spec.rows[20:40]


def test_short_first_page_stays_short_for_any_limit(make_condition):
    spec, api = _api(make_condition, extent=Extent.MORE_SHORT)
    for limit in (20, 10, 5):
        rows = _body(api.call(spec.target_tool, {**spec.target_args, "limit": limit}))["results"]
        assert len(rows) < limit


def test_invalid_paging_arguments_still_count_as_paging(make_condition):
    from fplp.env.server import MockAPI
    from fplp.tasks.specs import build_episode

    spec = build_episode(make_condition("has_more", "filtered_count", 0))
    api = MockAPI(spec)
    api.call(spec.target_tool, {**spec.target_args, "page": 2, "limit": "max"})
    api.call(spec.target_tool, {**spec.target_args, "limit": float("inf")})   # JSON Infinity
    assert api.calls[0]["error"] and api.calls[0]["paging"]
    assert api.calls[1]["error"] and not api.calls[1]["paging"]


@pytest.mark.parametrize(("conflict", "base", "contradiction"), [
    ("visible_conflict_total", "has_more", {"has_more": False, "total_count": "n"}),
    ("visible_conflict_note", "next_cursor", {"next_cursor": None, "message": "Showing results 1-20 of n."}),
])
def test_visible_conflicts_show_the_contradiction_on_page_one_only(conflict, base, contradiction):
    import json

    from fplp.conditions import Condition
    from fplp.env.server import MockAPI
    from fplp.signals.formats import Conflict, SignalForm
    from fplp.tasks.specs import build_episode

    spec = build_episode(Condition(signal_form=SignalForm(base), task_type="filtered_count", item=0,
                                   conflict=Conflict(conflict), arm="conflict"))
    n = len(spec.rows)
    api = MockAPI(spec)
    page1 = json.loads(api.call(spec.target_tool, spec.target_args))
    page1.pop("results")
    expected = {k: (n if v == "n" else v.replace(" n.", f" {n}.") if isinstance(v, str) else v) for k, v in contradiction.items()}
    assert page1 == expected and n > 20
    page2 = json.loads(api.call(spec.target_tool, {**spec.target_args, "page": 2}))
    assert "total_count" not in page2 and "message" not in page2   # later pages are truthful and plain
