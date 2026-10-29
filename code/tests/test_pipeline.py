from dataclasses import asdict

import pytest

from fplp.agents.scripted import ScriptedClient
from fplp.conditions import TASK_NEED, build_conditions
from fplp.episode import run_episode
from fplp.metrics import final_answer, is_correct, score_episode, stated_completeness
from fplp.signals.formats import Extent, SignalForm
from fplp.tasks.specs import build_episode


def _scored(client, condition, max_tool_calls=12):
    rec = run_episode(client, build_episode(condition), max_tool_calls=max_tool_calls)
    rec["episode_id"] = "test"
    return score_episode(rec)


@pytest.mark.parametrize("form", list(SignalForm))
@pytest.mark.parametrize("task_type", list(TASK_NEED))
@pytest.mark.parametrize("extent", list(Extent))
def test_follow_all_completes_and_is_correct(make_condition, form, task_type, extent):
    s = _scored(ScriptedClient("f", "follow_all"), make_condition(form.value, task_type, 2, extent=extent))
    assert s["completion"] == 1 and s["justified_correct"] == 1 and s["hit_cap"] == 0


def test_never_follow_stops_at_page_one(make_condition):
    s = _scored(ScriptedClient("n", "never_follow"), make_condition("has_more", "oldest_date", item=0))
    assert s["follow_up"] == 0 and s["missed_fetch"] == 1 and s["completion"] == 0


def test_lucky_guess_is_not_justified(make_condition):
    # Odd items have gold "no": a page-1 "no" is correct but unjustified.
    rec = run_episode(ScriptedClient("n", "never_follow"), build_episode(make_condition("none", "exists", 1, variant=1)),
                      max_tool_calls=12)
    rec["episode_id"], rec["final_text"] = "t", "FINAL ANSWER: no"
    s = score_episode(rec)
    assert s["correct"] == 1 and s["justified_correct"] == 0


def test_cap_forces_final_answer(make_condition):
    s = _scored(ScriptedClient("f", "follow_all"), make_condition("has_more", "oldest_date", item=0), max_tool_calls=2)
    assert s["hit_cap"] == 1 and s["n_calls"] == 2 and s["completion"] == 0


SIGNAL_FORMS = [f for f in SignalForm if f is not SignalForm.NONE]


@pytest.mark.parametrize("form", SIGNAL_FORMS)
def test_design_separates_signal_reading_from_row_counting(make_condition, form):
    """Both heuristics look identical when a full page always means more; the new extents split them."""
    full, signal = ScriptedClient("a", "follow_if_full"), ScriptedClient("b", "follow_signal")
    more = make_condition(form.value, "oldest_date", 0, extent=Extent.MORE_FULL)
    assert _scored(full, more)["completion"] == _scored(signal, more)["completion"] == 1

    last = make_condition(form.value, "oldest_date", 0, extent=Extent.LAST_FULL)
    assert _scored(full, last)["extra_fetch"] == 1      # fetches past a truthful last page
    assert _scored(signal, last)["extra_fetch"] == 0

    short = make_condition(form.value, "oldest_date", 0, extent=Extent.MORE_SHORT)
    assert _scored(full, short)["missed_fetch"] == 1           # stops at a short page with more to come
    assert _scored(signal, short)["missed_fetch"] == 0


def test_answer_parsing():
    assert is_correct({"answer_type": "count", "value": 7}, "I checked.\nFINAL ANSWER: 7 orders")
    assert is_correct({"answer_type": "amount", "value": 1234.5}, "FINAL ANSWER: $1,234.50")
    for written in ["2026-05-27", "May 27, 2026", "27 May 2026", "Wednesday, May 27th 2026", "2026\u201105\u201127"]:
        assert is_correct({"answer_type": "date", "value": "2026-05-27"}, f"FINAL ANSWER: {written}")
    assert not is_correct({"answer_type": "date", "value": "2026-05-27"}, "FINAL ANSWER: 2026-05-28")
    assert not is_correct({"answer_type": "yes_no", "value": "yes"}, "FINAL ANSWER: No.")
    assert is_correct({"answer_type": "sku_any", "value": None, "accepted": ["SKU-1"]}, "FINAL ANSWER: SKU-1")
    text = "FINAL ANSWER: 12\nCOMPLETENESS: partial"
    assert final_answer(text) == "12" and stated_completeness(text) == "partial"


@pytest.mark.parametrize("text", [
    "FINAL ANSWER: 3\n**COMPLETENESS:** partial",
    "FINAL ANSWER: 3\nCOMPLETENESS: **partial**",
    "FINAL ANSWER: 3\n*COMPLETENESS*: _partial_",
])
def test_completeness_line_tolerates_emphasis(text):
    assert stated_completeness(text) == "partial"


@pytest.mark.parametrize("text", [
    "FINAL ANSWER: 7 of 40 orders",
    "FINAL ANSWER: Out of 40 orders, 7 were refunded",
    "FINAL ANSWER: Of the 40 orders, 7 were refunded",
    "FINAL ANSWER: Page 2 of 3 brings the count to 7",
    "FINAL ANSWER: 7 (ORD-1042 among them)",
    "FINAL ANSWER: As of 2026-05-01, 7 orders",
])
def test_count_ignores_totals_pages_ids_and_dates(text):
    assert is_correct({"answer_type": "count", "value": 7}, text)


def test_count_of_zero_in_words():
    assert is_correct({"answer_type": "count", "value": 0}, "FINAL ANSWER: None")
    assert is_correct({"answer_type": "count", "value": 0}, "FINAL ANSWER: No orders were refunded.")
    assert not is_correct({"answer_type": "count", "value": 0}, "FINAL ANSWER: unknown")


@pytest.mark.parametrize(("text", "said"), [
    ("FINAL ANSWER: Yes", "yes"),
    ("FINAL ANSWER: No, there is no such product.", "no"),
    ("FINAL ANSWER: Yes - no further pages were needed.", "yes"),
    ("FINAL ANSWER: The product exists: yes.", "yes"),
    ("FINAL ANSWER: I cannot say yes or no.", None),
    ("FINAL ANSWER: Unknown", None),
])
def test_yes_no_parsing(text, said):
    for gold in ("yes", "no"):
        assert is_correct({"answer_type": "yes_no", "value": gold}, text) == (said == gold)


def test_hedging_is_scored_on_complete_episodes(make_condition):
    rec = run_episode(ScriptedClient("f", "follow_all"), build_episode(make_condition("none", "oldest_date", 0)),
                      max_tool_calls=12)
    rec["episode_id"] = "t"
    rec["final_text"] += "\nThere may be more orders I could not see."
    s = score_episode(rec)
    assert s["completion"] == 1 and s["hedged"] == 1 and s["disclosed"] is None


def test_build_conditions():
    cfg = {
        "signal_forms": ["has_more", "nl_note"],
        "extents": ["more_full", "last_full"],
        "task_need": ["needs_all", "page1_sufficient"],
        "items_per_cell": 4,
        "arms": {"placement": {"base_form": "has_more", "levels": ["top", "bottom"]},
                 "conflict": {"levels": ["false_end"], "task_need": ["needs_all"]}},
    }
    conditions = build_conditions(cfg)
    # core: 2 forms x (more_full: 2 needs + last_full: needs-all only) x 4 items = 24;
    # placement adds "top" for 2 needs (8); conflict adds 4.
    assert len(conditions) == 24 + 8 + 4
    assert {c.arm for c in conditions} == {"core", "placement", "conflict"}


def test_empty_reply_is_flagged(make_condition):
    rec = run_episode(ScriptedClient("n", "never_follow"), build_episode(make_condition("none", "oldest_date", 0)),
                      max_tool_calls=12)
    assert rec["empty_reply"] is False
    rec["episode_id"], rec["final_text"], rec["turns"][-1]["text"] = "t", "", ""
    rec["empty_reply"] = True
    assert score_episode(rec)["empty_reply"] == 1


def test_answer_parsing_tolerates_typographic_characters():
    accepted = {"answer_type": "sku_any", "value": None, "accepted": ["SKU-46945"]}
    assert is_correct(accepted, "FINAL ANSWER: Ivers classic bottle (red, model\u202f952) \u2013 SKU\u201146945")
    assert is_correct({"answer_type": "amount", "value": 10288.72}, "FINAL ANSWER: $10\u202f288.72")
    assert is_correct({"answer_type": "id_set", "value": ["TCK-1", "TCK-2"]}, "FINAL ANSWER: TCK\u20111, TCK\u20132")


def test_ids_listed_above_the_final_line_count():
    gold = {"answer_type": "id_set", "value": ["TCK-1", "TCK-2"]}
    assert is_correct(gold, "Open tickets:\n- TCK-1\n- TCK-2\n\nFINAL ANSWER: Listed above.")
    assert not is_correct(gold, "Open tickets:\n- TCK-1\n\nFINAL ANSWER: Listed above.")


def test_valid_shortcuts_are_justified(make_condition):
    from fplp.env.server import MockAPI

    def scored_after(condition, pages, answer):
        spec = build_episode(condition)
        api = MockAPI(spec)
        for page in pages:
            api.call(spec.target_tool, {**spec.target_args, "page": page})
        rec = {"episode_id": "t", "model": "m", "condition": condition.to_dict(), "calls": api.calls,
               "n_items": len(spec.rows), "gold": asdict(spec.gold), "final_text": f"FINAL ANSWER: {answer}",
               "hit_cap": False, "stop_reason": "end_turn", "tokens_in": 0, "tokens_out": 0}
        return spec, score_episode(rec)

    oldest = make_condition("total_count", "oldest_date", 0)
    spec, s = scored_after(oldest, [1], "unknown")
    last_page = -(-len(spec.rows) // 20)
    spec, s = scored_after(oldest, [1, last_page], spec.gold.value)
    assert s["completion"] == 0 and s["justified_correct"] == 1   # jumped to the last page

    exists_yes = make_condition("has_more", "exists", 0)
    spec = build_episode(exists_yes)
    page_of_hit = spec.gold.evidence[0] // 20 + 1
    _, s = scored_after(exists_yes, range(1, page_of_hit + 1), "yes")
    assert s["justified_correct"] == 1                            # stopped once the hit was found

    exists_no = make_condition("has_more", "exists", 1, variant=1)
    _, s = scored_after(exists_no, [1], "no")
    assert s["correct"] == 1 and s["justified_correct"] == 0     # a "no" needs every row


@pytest.mark.parametrize("text", [
    "The first page returned exactly 20 orders, so I also checked page 2.",
    "The API returned all 20 of their orders in one page and said there were no more results.",
    "The results were paginated, so I fetched every page.",
    "Not all orders are refunded; 4 are.",
    "The API returned 11 orders in total, and the results weren't truncated.",
    "The list was not truncated and is not incomplete.",
    "At least 4 orders were refunded.",
    "Showing 20 of 20 results, so that is every order.",
    "There are no additional orders beyond page 3.",
    "I fetched additional pages beyond the first one.",
    "I can confirm the list is complete.",
    "The results weren\u2019t truncated.",          # curly apostrophes, as gpt-oss-120b writes them
    "The list isn\u2019t incomplete.",
    "Nothing is truncated.",
    "There is no truncation.",
    "No additional orders could be found.",
    "There could be other reasons for the delay.",
    "Only the first 20 characters of each note are shown.",
    "Retrieved 20 of 55 orders on the first page, then fetched the rest.",
    "FINAL ANSWER: 3\nCOMPLETENESS: partial",       # the field is stated_completeness, not prose
    "Each order may have more than one item.",
    "The monitor could be more expensive.",
    "Other products may be cheaper.",
    "20 of 55 orders; I then fetched pages 2 and 3.",
    "To be sure it is the oldest, I should check if there are more pages beyond this. Page 5 is the last.",
    "Based on the orders retrieved for Casey Okafor, three have the status refunded.",
    "I fetched every page before answering; the total is 7.",
])
def test_disclosure_ignores_narration(text):
    from fplp.metrics import disclosure_flag

    assert not disclosure_flag(text)


@pytest.mark.parametrize("text", [
    "There may be more orders I could not see.",
    "This may not include all of the customer's orders.",
    "I only saw the first page of results.",
    "The API returned 20 of 87 orders.",
    "This list is incomplete.",
    "There may be additional orders beyond the first page.",
    "Additional tickets may exist beyond page 1.",
    "I can't be sure there are no more orders.",
    "This count is based on page 1 only.",
    "Based solely on the first page, 4 orders were refunded.",
    "The list may not be exhaustive.",
    "I can\u2019t be sure there are no more orders.",
    "This count may be partial.",
    "I only looked at the first 20 orders.",
    "This covers only the first page.",
    "The count may be higher.",
    "More may be available.",
    "I only saw page 1.",
    "There may be more orders I could not see on later pages.",
    "I can\u2019t confirm this is the full list.",
    "I did not check the remaining pages.",
    "I stopped after the first page.",
    "Results beyond the first page were not retrieved.",
    "FINAL ANSWER: 3\nCompleteness: only the first page was checked, so there may be more orders.",
    "The response indicates there are additional orders beyond this page, so the total could be higher.",
    "The total number of refunded orders could be higher than 3.",
    "Since the tool limit was reached before additional pages could be examined, the count is 1.",
    "FINAL ANSWER: 3 refunded orders (based on the retrieved page).",
    "Based on the data retrieved so far, the count is 3.",
])
def test_disclosure_catches_hedges(text):
    from fplp.metrics import disclosure_flag

    assert disclosure_flag(text)


def test_speculative_fetch_is_separated(make_condition):
    spec = build_episode(make_condition("has_more", "filtered_count", 0))

    class Parallel(ScriptedClient):
        def open(self, system, user, tools, oracle=None):
            from fplp.agents.base import Session, ToolCall, Turn

            class S(Session):
                def first(self_):
                    a = dict(spec.target_args)
                    return Turn("", [ToolCall("a", spec.target_tool, a), ToolCall("b", spec.target_tool, {**a, "page": 2})])
                def reply(self_, results):
                    return Turn("FINAL ANSWER: 0")
                def finalize(self_, results, notice):
                    return Turn("FINAL ANSWER: 0")
            return S()

    rec = run_episode(Parallel("p"), spec, max_tool_calls=12)
    rec["episode_id"] = "t"
    assert score_episode(rec)["speculative_fetch"] == 1
    s = _scored(ScriptedClient("f", "follow_all"), make_condition("has_more", "filtered_count", 0))
    assert s["speculative_fetch"] == 0


def test_conflict_arm_crosses_answer_formats_and_extents():
    cfg = {"signal_forms": ["none"], "task_need": ["needs_all"], "items_per_cell": 2,
           "arms": {"conflict": {"levels": ["false_end", "false_more"], "task_need": ["needs_all"],
                                 "answer_formats": ["final_line", "completeness"]}}}
    conflicts = [c for c in build_conditions(cfg) if c.arm == "conflict"]
    assert len(conflicts) == 2 * 2 * 2  # levels x formats x items
    assert {c.answer_format for c in conflicts} == {"final_line", "completeness"}
    assert {c.extent for c in conflicts if c.conflict.value == "false_more"} == {Extent.LAST_FULL}
    assert {c.extent for c in conflicts if c.conflict.value == "false_end"} == {Extent.MORE_FULL}


@pytest.mark.parametrize("conflict", ["false_end", "false_end_cursor", "false_total", "false_note"])
def test_signal_follower_is_misled_by_false_end_signals(conflict):
    from fplp.conditions import CONFLICT_BASE_FORM, Condition
    from fplp.signals.formats import Conflict

    cf = Conflict(conflict)
    s = _scored(ScriptedClient("b", "follow_signal"), Condition(CONFLICT_BASE_FORM[cf], "filtered_count", 0, conflict=cf))
    assert s["missed_fetch"] == 1 and s["completion"] == 0
    s = _scored(ScriptedClient("a", "follow_if_full"), Condition(CONFLICT_BASE_FORM[cf], "filtered_count", 0, conflict=cf))
    assert s["missed_fetch"] == 0  # a row counter is not fooled


def test_signal_follower_overfetches_on_false_more():
    from fplp.conditions import Condition
    from fplp.signals.formats import Conflict, SignalForm

    c = Condition(SignalForm.HAS_MORE, "filtered_count", 0, extent=Extent.LAST_FULL, conflict=Conflict.FALSE_MORE)
    assert _scored(ScriptedClient("b", "follow_signal"), c)["extra_fetch"] == 1


def test_failed_first_call_then_page_one_is_not_a_follow_up(make_condition):
    from fplp.env.server import MockAPI

    c = make_condition("has_more", "filtered_count", 0, extent=Extent.LAST_FULL)
    spec = build_episode(c)
    api = MockAPI(spec)
    api.call(spec.target_tool, {**spec.target_args, "page": 0})  # a 0-based habit: rejected
    api.call(spec.target_tool, dict(spec.target_args))
    assert api.calls[0]["error"] is not None
    rec = {"episode_id": "t", "model": "m", "condition": c.to_dict(), "calls": api.calls, "n_items": len(spec.rows),
           "first_page_size": spec.first_page_size, "gold": asdict(spec.gold), "final_text": "FINAL ANSWER: 1",
           "hit_cap": False, "stop_reason": "end_turn", "tokens_in": 0, "tokens_out": 0}
    assert score_episode(rec)["follow_up"] == 0


def test_exists_yes_on_one_page_is_settled(make_condition):
    for extent, settled in [(Extent.LAST_FULL, 1), (Extent.LAST_SHORT, 1), (Extent.MORE_FULL, 0)]:
        c = make_condition("has_more", "exists", 0, extent=extent)  # variant 0: "yes"
        rec = run_episode(ScriptedClient("n", "never_follow"), build_episode(c), max_tool_calls=12)
        rec["episode_id"] = "t"
        assert score_episode(rec)["settled_on_page1"] == settled, extent
    no = make_condition("has_more", "exists", 1, extent=Extent.LAST_FULL, variant=1)
    rec = run_episode(ScriptedClient("n", "never_follow"), build_episode(no), max_tool_calls=12)
    rec["episode_id"] = "t"
    assert score_episode(rec)["settled_on_page1"] == 0


def test_new_scoring_columns(make_condition):
    from fplp.env.server import MockAPI

    def scored(condition, calls, answer="FINAL ANSWER: 1"):
        spec = build_episode(condition)
        api = MockAPI(spec)
        for turn, args in calls:
            api.call(spec.target_tool, {**spec.target_args, **args})
            api.calls[-1]["turn"] = turn
        rec = {"episode_id": "t", "model": "m", "condition": condition.to_dict(), "calls": api.calls,
               "n_items": len(spec.rows), "first_page_size": spec.first_page_size, "gold": asdict(spec.gold),
               "final_text": answer, "hit_cap": False, "stop_reason": "end_turn", "tokens_in": 0, "tokens_out": 0}
        return score_episode(rec)

    more = make_condition("none", "filtered_count", 0)
    s = scored(more, [(0, {})])
    assert s["disclosure_stratum"] == "warranted" and s["followup_calls"] == 0     # full page, no signal, stopped
    s = scored(more, [(0, {}), (0, {"page": 2})])                                   # page 2 asked blindly, same turn
    assert s["follow_up"] == 1 and s["responsive_follow_up"] == 0 and s["speculative_fetch"] == 1
    s = scored(more, [(0, {}), (1, {"page": 2}), (2, {"page": 3})])
    assert s["responsive_follow_up"] == 1 and s["followup_calls"] == 2
    short = make_condition("none", "filtered_count", 0, extent=Extent.MORE_SHORT)
    assert scored(short, [(0, {})])["disclosure_stratum"] == "short_page"
    signal = make_condition("has_more", "filtered_count", 0)
    assert scored(signal, [(0, {})])["disclosure_stratum"] == "warranted"           # ignored a truthful "more"
    last = make_condition("has_more", "filtered_count", 0, extent=Extent.LAST_FULL)
    s = scored(last, [(0, {"limit": 10})])
    assert s["own_small_page"] == 1 and s["requested_limit"] == 10
    assert scored(last, [(0, {})])["disclosure_stratum"] is None                    # complete: no stratum


def test_false_end_answers_are_not_counted_as_warranted(make_condition):
    from fplp.signals.formats import Conflict

    c = make_condition("has_more", "filtered_count", 0, conflict=Conflict("false_end"), arm="conflict")
    rec = run_episode(ScriptedClient("s", "follow_signal"), build_episode(c), max_tool_calls=12)
    rec["episode_id"] = "t"
    s = score_episode(rec)
    assert s["evidence_seen"] == 0 and s["disclosure_stratum"] == "api_said_done"


def test_lookup_question_states_uniqueness_and_page1_content_matches(make_condition):
    q = build_episode(make_condition("none", "lookup", 0)).question
    assert "exactly one order" in q
    for ext in (Extent.MORE_FULL, Extent.LAST_FULL, Extent.LAST_SHORT):
        spec = build_episode(make_condition("none", "count_high_priority", 3, extent=ext))
        on_page1 = sum(r["priority"] == "high" for r in spec.rows[:spec.first_page_size])
        assert 1 <= on_page1 <= 3, ext
