"""Amendment 2's exploratory variants: total_matches renders the same total under another name, the
plain wording drops only "when it includes one", and neither changes an existing episode's id."""

import json

from fplp.agents.scripted import signals_more
from fplp.conditions import Condition, build_conditions, episode_id
from fplp.config import load_run_config
from fplp.env.tools import tool_schemas
from fplp.signals.formats import Extent, SignalForm
from fplp.signals.render import render_page


def page(form, total, has_next):
    return render_page([{"order_id": "ORD-1"}] * 20, form, start=0, total=total, has_next=has_next,
                       next_cursor="tok", next_url="/orders?cursor=tok")


def test_total_matches_is_total_count_renamed():
    for total, more in [(87, True), (20, False)]:
        a, b = json.loads(page(SignalForm.TOTAL_COUNT, total, more)), json.loads(page(SignalForm.TOTAL_MATCHES, total, more))
        assert a["total_count"] == b["total_matches"] == total and set(a) - {"total_count"} == set(b) - {"total_matches"}
    assert signals_more(page(SignalForm.TOTAL_MATCHES, 87, True), 20)
    assert not signals_more(page(SignalForm.TOTAL_MATCHES, 20, False), 20)


def descriptions(**kw):
    tool = tool_schemas(20, **kw)[0]
    return tool["description"], tool["parameters"]["properties"]["cursor"].get("description", "")


def test_plain_wording_drops_only_the_clause():
    default_desc, default_cursor = descriptions(documented=True)
    plain_desc, plain_cursor = descriptions(documented=True, wording="plain")
    assert "when it includes one" in default_desc and "when it includes one" in default_cursor
    assert "when it includes one" not in plain_desc + plain_cursor
    assert plain_desc == default_desc.replace(", when it includes one", "")
    assert plain_cursor == default_cursor.replace(", when it includes one", "")
    assert descriptions(documented=False) == descriptions(documented=False, wording="plain")  # nothing to change


def test_default_wording_leaves_ids_unchanged_and_plain_gets_its_own():
    base = Condition(signal_form=SignalForm.NONE, task_type="filtered_count", item=3, extent=Extent.LAST_FULL)
    assert "doc_wording" not in base.to_dict()                       # the record is as before the arm existed
    plain = Condition(signal_form=SignalForm.NONE, task_type="filtered_count", item=3, extent=Extent.LAST_FULL,
                      doc_wording="plain")
    assert plain.to_dict()["doc_wording"] == "plain" and Condition.from_dict(plain.to_dict()) == plain
    model = {"name": "m", "provider": "scripted"}
    assert episode_id(model, base, 12) != episode_id(model, plain, 12)


def test_robustness_config_plans_the_registered_cells():
    cfg = load_run_config("configs/runs/robustness.yaml", require_items=True)
    conds = build_conditions(cfg)
    plain = [c for c in conds if c.doc_wording == "plain"]
    assert {c.signal_form.value for c in plain} == {"none", "has_more", "nl_note_json"}
    assert {c.extent.value for c in conds} == {"more_full", "last_full"}
    assert len(conds) == 1600 and len(plain) == 600
    assert sum(c.signal_form is SignalForm.TOTAL_MATCHES for c in conds) == 200


def test_robustness_checks_on_scripted_agents(tmp_path):
    from pathlib import Path

    import pandas as pd

    from fplp import cli
    from fplp.analysis.robustness import CHECKS, run

    cfg = tmp_path / "rob.yaml"
    text = Path("configs/runs/robustness.yaml").read_text().replace("items_per_cell: 100", "items_per_cell: 12")
    cfg.write_text(text.replace("models: [gpt-oss-120b]", "models: [scripted-hybrid]"))
    models = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env"), "--workers", "4"])
    cli.main(["score", str(tmp_path / "raw" / "robustness"), "--out", str(tmp_path / "s.csv")])
    t = run(pd.read_csv(tmp_path / "s.csv"), n_boot=100)
    assert list(t["check"]) == [c[0] for c in CHECKS] and (t["n"] > 0).all()
    assert (t["diff"] == 0).all()    # a scripted agent reads neither the description nor the field's name


def test_reference_table_matches_the_reference_agent(tmp_path):
    import pandas as pd

    from fplp.analysis.reference import table

    df = pd.DataFrame([{"model": model, "arm": "core", "signal_form": "none", "conflict": None, "extent": "more_full",
                        "task_need": "needs_all", "answer_format": "final_line", "task_type": "filtered_count",
                        "item": item, "follow_up": fetched, "settled_on_page1": 0, "empty_reply": 0,
                        "stop_reason": "end_turn"}
                       for model, fetched in [("scripted-signal", 0), ("scripted-if-full", 1), ("scripted-hybrid", 1),
                                              ("m", 1)]
                       for item in range(4)])
    t = table(df, df, "m").set_index("cell").loc["no hint, more rows behind a full page"]
    assert (t["m"], t["follows the hint"], t["counts rows"], t["hint, else count"]) == (100, 0, 100, 100)


def test_multiplicity_corrections():
    import pandas as pd

    from fplp.analysis.multiplicity import benjamini_hochberg, run

    # thresholds .05 * i / 4 = .0125, .025, .0375, .05 against the sorted p values
    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.5]) == [True, False, False, False]
    assert benjamini_hochberg([0.01, 0.036, 0.03, 0.5]) == [True, True, True, False]   # step-up: .036 rescues .03
    detail = pd.DataFrame([
        {"model": "m", "family": "amended", "hypothesis": "A1", "part": "a", "test": f"t{i}", "diff": 0.2, "p": p,
         "supported": True} for i, p in enumerate([0.001, 0.002, 0.02])
    ] + [{"model": "m", "family": "amended", "hypothesis": "H3", "part": "a", "test": "bound", "diff": 0.9, "p": None,
          "supported": False}])
    t = run(detail)
    assert len(t) == 3 and t["holm_all"].tolist() == [True, True, True]   # .02 <= .05/1 at the last step
    detail.loc[2, "p"] = 0.04
    assert run(detail)["holm_all"].tolist() == [True, True, True]
    detail.loc[2, "p"] = 0.06
    assert run(detail)["holm_all"].tolist() == [True, True, False]


def test_disclosure_screen_net_catches_what_the_flag_missed():
    from fplp.analysis.disclosure import WIDE_NET
    from fplp.metrics import disclosure_flag

    missed = "Here are the IDs of the open support tickets returned (first 20 of 62):"
    assert not disclosure_flag(missed) and WIDE_NET.search(missed)
    assert not WIDE_NET.search("Skyler Haddad has 3 orders with the status refunded. FINAL ANSWER: 3")
