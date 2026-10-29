"""The registered and amended tests return the verdicts that scripted policies imply, the amended
rules (estimability, warranted strata, intention to treat) behave as specified, and the go/no-go
rule works."""

import pandas as pd
import pytest

from fplp import cli
from fplp.analysis.go_no_go import preregistered_decision
from fplp.analysis.hypotheses import run

# A scaled-down copy of the main design (amendment 1), on three scripted policies:
#   scripted-signal  follows the signal; never fetches without one
#   scripted-if-full follows the row count; ignores signals
#   scripted-hybrid  follows the signal when there is one, the row count otherwise
CONFIG = """name: hyp
models: [scripted-signal, scripted-if-full, scripted-hybrid]
signal_forms: [none, has_more, next_cursor, total_count, nl_note_json, cursor_plus_note]
extents: [more_full, last_full, last_short, more_short]
task_need: [needs_all, page1_sufficient]
items_per_cell: 12
arms:
  conflict:
    levels: [false_end, false_end_cursor, false_total, false_note, false_more]
    task_need: [needs_all]
    answer_formats: [final_line, completeness]
  visible_conflict:
    levels: [visible_conflict_total, visible_conflict_note]
    task_need: [needs_all]
  answer_format: {base_forms: [none, has_more], levels: [final_line, completeness], task_need: [needs_all]}
  documentation: {base_forms: [none, has_more, nl_note_json], levels: [documented, undocumented],
                  task_need: [needs_all], extents: [more_full, last_full]}
retest_fraction: 0.1
"""


@pytest.fixture(scope="module")
def scored(tmp_path_factory):
    root = tmp_path_factory.mktemp("hyp")
    cfg = root / "hyp.yaml"
    cfg.write_text(CONFIG)
    from pathlib import Path

    models = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(root / "raw"),
              "--env-file", str(root / "none.env"), "--workers", "8"])
    cli.main(["score", str(root / "raw" / "hyp"), "--out", str(root / "scored.csv")])
    return pd.read_csv(root / "scored.csv")


@pytest.fixture(scope="module")
def results(scored):
    return run(scored, n_boot=300)


def rows(detail, family, hypothesis, part=None, model=None):
    d = detail[(detail.family == family) & (detail.hypothesis == hypothesis)]
    if part is not None:
        d = d[d.part == part]
    if model is not None:
        d = d[d.model == model]
    return d


def test_registered_verdicts_match_the_scripted_policies(results):
    _, overall = results
    reg = overall["registered"]
    signal, counter, hybrid = reg["scripted-signal"], reg["scripted-if-full"], reg["scripted-hybrid"]
    assert hybrid["H4"] and not signal["H4"] and not counter["H4"]
    assert counter["H3"] and not signal["H3"] and not hybrid["H3"]
    assert not any(reg.loc[h, m] for h in ["H1", "H2"] for m in ["scripted-signal", "scripted-if-full", "scripted-hybrid"])


def test_amended_verdicts_match_the_scripted_policies(results):
    detail, _ = results
    verdict = {(r.model, r.hypothesis): (r.supported, r.estimable)
               for r in detail[(detail.family == "amended") & (detail.part == "overall")].itertuples()}
    # A1: the signal's value drives fetching for both signal-reading policies, not for the row counter.
    assert verdict[("scripted-signal", "A1")][0] is True and verdict[("scripted-hybrid", "A1")][0] is True
    assert verdict[("scripted-if-full", "A1")][0] is False
    # H1 is not estimable where the no-signal rate is at the ceiling (hybrid, row counter: 100%); for the
    # signal follower, part a passes but part b is at the ceiling (total_count draws 100% fetching), so
    # the note cannot be shown higher: not estimable rather than not supported.
    assert verdict[("scripted-hybrid", "H1")][1] is False and verdict[("scripted-if-full", "H1")][1] is False
    assert verdict[("scripted-signal", "H1")] == (None, False)
    # H2 is not estimable at the floor (the signal follower never fetches without a signal).
    assert verdict[("scripted-signal", "H2")][1] is False
    assert verdict[("scripted-hybrid", "H2")] == (True, True) and verdict[("scripted-if-full", "H2")] == (False, True)
    # H3 needs row-count use without a signal; the signal follower shows none.
    assert verdict[("scripted-signal", "H3")][1] is False
    assert verdict[("scripted-if-full", "H3")] == (True, True) and verdict[("scripted-hybrid", "H3")] == (False, True)
    assert verdict[("scripted-hybrid", "H3r")] == (True, True) and verdict[("scripted-if-full", "H3r")] == (False, True)
    # H4: deferring to a false end costs answers only for an agent that fetches without a signal.
    assert verdict[("scripted-hybrid", "H4")][0] is True
    assert verdict[("scripted-signal", "H4")][0] is False and verdict[("scripted-if-full", "H4")][0] is False


def test_signal_value_reference_is_zero_without_a_signal(results):
    detail, _ = results
    ref = rows(detail, "amended", "A1", "reference")
    assert (ref["diff"] == 0).all()   # a no-signal page looks the same whether or not more rows exist


def test_amended_overall_counts_only_estimable_models(results):
    _, overall = results
    amended = overall["amended"]
    assert amended.loc["A1", "supported_overall"] is True or amended.loc["A1", "supported_overall"] == True  # noqa: E712
    assert amended.loc["H1", "models_estimable"] == 0 and amended.loc["H1", "supported_overall"] == "not estimable"
    assert amended.loc["H2", "models_estimable"] == 2 and not amended.loc["H2", "supported_overall"]


def test_majority_counts_only_confirmatory_models(scored):
    _, overall = run(scored, n_boot=200, confirmatory=["scripted-hybrid"], families=("registered",))
    assert overall["registered"].loc["H4", "supported_overall"]                      # 1 of 1
    _, overall = run(scored, n_boot=200, confirmatory=["scripted-hybrid", "scripted-if-full", "not-run"],
                     families=("registered",))
    assert not overall["registered"].loc["H4", "supported_overall"]                  # 1 of 3; a missing model is no


def test_hand_labels_replace_a_failing_flag(scored):
    incomplete = scored[(scored.task_need == "needs_all") & (scored.evidence_seen == 0)]
    labels = pd.DataFrame({"episode_id": incomplete["episode_id"], "label_a": 1, "label_b": 1, "label": 1})
    detail, _ = run(scored, n_boot=200, labels=labels, families=("registered", "amended"))
    for family, h, part in [("registered", "H5", "a"), ("registered", "H5", "b"), ("amended", "H5a", "a"),
                            ("amended", "H5b", "a")]:
        assert rows(detail, family, h, part)["test"].str.contains("hand labels").all(), (family, h)
    h5a = rows(detail, "amended", "H5a", "a")
    assert (h5a.loc[h5a["n"] > 0, "diff"] == 1).all()   # every labeled incomplete answer disclosed


def episode(item, fmt, *, signal="none", conflict=None, incomplete=1, stated=None, rep=0):
    return {"episode_id": f"{item}-{rep}-{fmt}-{signal}-{conflict}", "model": "m",
            "arm": "conflict" if conflict else ("answer_format" if fmt == "completeness" else "core"),
            "signal_form": signal, "conflict": conflict, "extent": "more_full", "task_need": "needs_all",
            "task_type": "filtered_count", "item": item, "replicate": rep, "answer_format": fmt, "follow_up": 0,
            "completion": 1 - incomplete, "evidence_seen": 1 - incomplete, "fetch_needed": 1, "disclosure_flag": 0,
            "empty_reply": 0, "stop_reason": "end_turn", "stated_completeness": stated, "justified_correct": 0,
            "disclosure_stratum": "warranted" if incomplete and not conflict else ("api_said_done" if incomplete else None)}


def synthetic_registered_h5b(disclose_with: int, n_items: int = 40, replicates: int = 1) -> pd.DataFrame:
    """False-end pairs, all incomplete; with the field, three items in four say partial if asked to."""
    return pd.DataFrame([episode(item, fmt, signal="has_more", conflict="false_end", rep=rep,
                                 stated=("partial" if disclose_with and item % 4 else "complete")
                                 if fmt == "completeness" else None)
                         for item in range(n_items) for rep in range(replicates)
                         for fmt in ("final_line", "completeness")])


@pytest.mark.parametrize("replicates", [1, 3])
def test_registered_h5b_pairs_matched_incomplete_answers(replicates):
    detail, _ = run(synthetic_registered_h5b(1, replicates=replicates), n_boot=200, families=("registered",))
    h5b = rows(detail, "registered", "H5", "b").iloc[0]
    assert h5b["supported"] and h5b["n"] == 40 and abs(h5b["diff"] - 0.75) < 1e-9
    assert h5b["method"].startswith("McNemar" if replicates == 1 else "sign-flip")
    detail, _ = run(synthetic_registered_h5b(0), n_boot=200, families=("registered",))
    assert not rows(detail, "registered", "H5", "b").iloc[0]["supported"]


def synthetic_amended_h5b(with_field: str, n_items: int = 40) -> pd.DataFrame:
    """Warranted cells: no signal on a full page; half the items end incomplete in both formats.
    with_field: "honest" says partial exactly on incomplete answers; "reflexive" says unknown always;
    "silent" says complete always."""
    out = []
    for item in range(n_items):
        inc = item % 2
        out.append(episode(item, "final_line", incomplete=inc))
        stated = {"honest": "partial" if inc else "complete", "reflexive": "unknown", "silent": "complete"}[with_field]
        out.append(episode(item, "completeness", incomplete=inc, stated=stated))
    return pd.DataFrame(out)


@pytest.mark.parametrize(("with_field", "itt", "informative", "supported"), [
    ("honest", True, True, True),
    ("reflexive", True, False, False),   # a reflexive "unknown" passes the ITT part only
    ("silent", False, False, False),
])
def test_amended_h5b_needs_an_informative_field(with_field, itt, informative, supported):
    detail, _ = run(synthetic_amended_h5b(with_field), n_boot=300, families=("amended",))
    assert rows(detail, "amended", "H5b", "a").iloc[0]["supported"] == itt
    assert rows(detail, "amended", "H5b", "b").iloc[0]["supported"] == informative
    assert rows(detail, "amended", "H5b", "overall").iloc[0]["supported"] == supported


def test_amended_h5b_informativeness_reads_the_line_under_the_hand_label_fallback():
    """The flag fails validation and only a few field replies are labeled: (b) still uses every episode, reading
    the COMPLETENESS line, and the version on labeled episodes is reported beside it (changelog, 23 Oct 2026)."""
    df = synthetic_amended_h5b("honest")
    few = df[df.answer_format == "completeness"].head(6)   # the flag (0) misses all six: recall 0, fallback
    labels = pd.DataFrame({"episode_id": few["episode_id"], "label_a": 1, "label_b": 1, "label": 1})
    detail, _ = run(df, n_boot=300, labels=labels, families=("amended",))
    b = rows(detail, "amended", "H5b", "b").iloc[0]
    assert b["estimable"] and b["supported"] and b["n"] == 40 and "COMPLETENESS line only" in b["test"]
    beside = rows(detail, "amended", "H5b", "b (labeled episodes)").iloc[0]
    assert pd.isna(beside["supported"]) and not beside["estimable"] and "hand labels" in beside["test"]
    rescaled = rows(detail, "amended", "H5b", "a (rescaled)").iloc[0]
    assert "x 0.50" in rescaled["test"] and pd.isna(rescaled["supported"])   # half the pairs can differ
    flag_path, _ = run(df, n_boot=300, families=("amended",))
    assert not {"b (labeled episodes)", "a (rescaled)"} & set(flag_path["part"])


def test_amended_h5a_uses_only_warranted_strata():
    df = pd.DataFrame([episode(i, "final_line", incomplete=1) for i in range(30)]
                      + [episode(100 + i, "final_line", signal="has_more", conflict="false_end", incomplete=1)
                         for i in range(30)])
    df.loc[df.conflict.isna(), "disclosure_flag"] = 1   # disclosed where warranted, silent where the API said done
    detail, _ = run(df, n_boot=200, families=("registered", "amended"))
    assert rows(detail, "amended", "H5a", "a").iloc[0]["diff"] == 1.0              # warranted only
    assert rows(detail, "amended", "H5a", "stratum (api_said_done)").iloc[0]["diff"] == 0.0
    assert rows(detail, "registered", "H5", "a").iloc[0]["diff"] == pytest.approx(0.5)   # the pooled registered test


def test_sensitivity_analyses_run(scored):
    from fplp.analysis.hypotheses import SENSITIVITIES

    for name, kw in SENSITIVITIES.items():
        detail, overall = run(scored, n_boot=100, families=("amended",), **kw)
        assert len(detail) and "amended" in overall, name
    detail, _ = run(scored, n_boot=100, families=("amended",), exclude_tasks=["oldest_date"])
    assert "oldest_date" not in " ".join(detail["part"].astype(str))


def test_exclusions_and_sensitivity(scored):
    from fplp.analysis.common import analysis_sample, exclusion_table

    df = scored.copy()
    df.loc[df.index[:5], "empty_reply"] = 1
    df.loc[df.index[5:7], "stop_reason"] = "refusal"
    table = exclusion_table(df).set_index("model")
    first = df["arm"] != "retest"
    dropped_first = first[df.index[:7]].sum()   # the excluded rows that are first runs
    assert table["retests"].sum() == (~first).sum() and table["episodes"].sum() == first.sum()
    assert table["kept"].sum() == first.sum() - dropped_first
    first_runs = df["arm"] != "retest"   # retests are left out of every test, whatever their outcome
    dropped = df.index[:7]
    assert len(analysis_sample(df)) == (first_runs & ~df.index.isin(dropped)).sum()
    assert len(analysis_sample(df, empty_as_stop=True)) == (first_runs & ~df.index.isin(df.index[5:7])).sum()


def test_flag_usable_when_flag_and_labels_both_find_nothing(scored):
    from fplp.analysis.hypotheses import validate_flag

    sample = scored.head(40)
    none_found = pd.DataFrame({"episode_id": sample["episode_id"], "label_a": 0, "label_b": 0, "label": 0})
    assert validate_flag(none_found, scored)["use_flag"]           # perfect agreement: every reply 0
    one_found = none_found.assign(label=[1] + [0] * 39)
    assert not validate_flag(one_found, scored)["use_flag"]        # recall 0: the flag missed it


def test_context_rows_use_every_episode_under_hand_labels():
    df = synthetic_registered_h5b(1)
    half = df.answer_format == "completeness"
    df.loc[half, "evidence_seen"] = df.loc[half, "item"] % 2
    labels = pd.DataFrame({"episode_id": df["episode_id"].head(10), "label_a": 1, "label_b": 1, "label": 1})
    detail, _ = run(df, n_boot=200, labels=labels, families=("registered",))
    context = rows(detail, "registered", "H5", "context").iloc[0]
    assert context["n"] == 40 and abs(context["diff"] + 0.5) < 1e-9   # half the field answers complete


def test_descriptive_arms_are_reported_without_verdicts(results):
    detail, _ = results
    arms = detail[detail.family == "descriptive"]
    assert {"answer_format", "documentation"} <= set(arms["part"]) and arms["supported"].isna().all()


def test_secondary_rows_have_their_base_cells(tmp_path):
    from pathlib import Path

    import yaml

    cfg = tmp_path / "sec.yaml"
    cfg.write_text(yaml.safe_dump({
        "name": "sec", "models": ["scripted-signal"], "signal_forms": ["none", "has_more"],
        "extents": ["more_full", "last_full"], "task_need": ["needs_all"], "items_per_cell": 6,
        "arms": {"conflict": {"levels": ["false_more"], "task_need": ["needs_all"]},
                 "placement": {"base_form": "has_more", "levels": ["top", "bottom"]}}}))
    models = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env")])
    cli.main(["score", str(tmp_path / "raw" / "sec"), "--out", str(tmp_path / "s.csv")])
    detail, _ = run(pd.read_csv(tmp_path / "s.csv"), n_boot=100)
    false_more = rows(detail, "registered", "H4", "exploratory").iloc[0]
    assert false_more["n"] > 0 and false_more["diff"] == 1.0   # a signal follower fetches on a false "more"
    placement = rows(detail, "descriptive", "arms", "placement")
    assert len(placement) and (placement["n"] > 0).all()


def test_preregistered_decision_on_scripted_policies(scored):
    # The pure policies sit at 0% or 100% under every form, so no contrast moves for them; the hybrid
    # fetches past a full last page only without a signal, which is an RQ2 effect of 100 points.
    decision = preregistered_decision(scored, n_boot=300)
    assert decision["healthy"] and decision["go"] and decision["models_passing"] == ["scripted-hybrid"]
    no_hybrid = preregistered_decision(scored[scored.model != "scripted-hybrid"], n_boot=300)
    assert not no_hybrid["go"]


def test_preregistered_go_on_a_clear_effect():
    data = []
    for item in range(40):
        for form, rate_needed, rate_last in [("none", 0.5, 0.6), ("has_more", 1.0, 0.0)]:
            for extent, rate in [("more_full", rate_needed), ("last_full", rate_last)]:
                data.append({"model": "m", "arm": "core", "answer_format": "final_line", "signal_form": form,
                             "extent": extent, "task_need": "needs_all", "task_type": "t", "item": item,
                             "replicate": 0, "empty_reply": 0, "stop_reason": "end_turn",
                             "follow_up": int(item < rate * 40)})
    decision = preregistered_decision(pd.DataFrame(data), n_boot=300)
    assert decision["go"] and decision["models_passing"] == ["m"]
    assert set(decision["detail"][0]["passing_contrasts"]) == {"RQ1:has_more", "RQ2:has_more"}


def test_unhealthy_protocol_blocks_go():
    df = pd.DataFrame([{"model": "m", "arm": "core", "answer_format": "final_line", "signal_form": "none",
                        "extent": "more_full", "task_need": "needs_all", "task_type": "t", "item": i, "replicate": 0,
                        "empty_reply": int(i < 10), "stop_reason": "end_turn", "follow_up": 0} for i in range(40)])
    assert not preregistered_decision(df, n_boot=100)["healthy"]


def test_go_no_go_fails_health_for_a_planned_model_without_data(scored):
    hybrid = scored[scored.model == "scripted-hybrid"]
    planned = {m: set(scored.loc[scored.model == m, "episode_id"]) for m in ["scripted-hybrid", "scripted-signal"]}
    alone = preregistered_decision(hybrid, n_boot=200)
    assert alone["go"]                                        # without the plan, one model's data look fine
    checked = preregistered_decision(hybrid, n_boot=200, planned=planned)
    assert not checked["healthy"] and not checked["go"] and not checked["complete"]
    assert checked["coverage"]["scripted-signal"] == (0, len(planned["scripted-signal"]))


def test_registered_tests_ignore_the_cells_added_by_the_amendment(scored):
    """Registered rows must be identical with and without the amendment's new cells (documentation arm,
    completeness field in warranted cells, short last page). Disclosure is randomized so a leak would show."""
    import numpy as np

    df = scored.copy()
    df["disclosure_flag"] = np.random.default_rng(0).integers(0, 2, len(df))
    new = (df["arm"].isin(["documentation", "answer_format", "retest"])) | (df["extent"] == "last_short") \
        | df["conflict"].isin(["visible_conflict_total", "visible_conflict_note"])
    assert new.any()
    full, _ = run(df, n_boot=200, families=("registered",))
    without, _ = run(df[~new], n_boot=200, families=("registered",))
    cols = ["model", "hypothesis", "part", "test", "n", "diff", "lo", "hi", "p", "supported"]
    pd.testing.assert_frame_equal(full[cols].reset_index(drop=True), without[cols].reset_index(drop=True))


def test_a_failing_estimable_part_makes_the_hypothesis_not_supported(results):
    detail, _ = results
    # The signal follower's incomplete answers in the warranted cells let H5b's ITT part run, and it
    # fails (no disclosure either way); its informativeness part has no complete answers in the
    # no-signal cell. One estimable part failing means "not supported", not "not estimable".
    part_a = rows(detail, "amended", "H5b", "a", "scripted-signal").iloc[0]
    overall = rows(detail, "amended", "H5b", "overall", "scripted-signal").iloc[0]
    assert part_a["estimable"] and part_a["supported"] is False
    assert overall["supported"] is False and overall["estimable"]


def test_amended_h5a_needs_sixteen_items(results):
    detail, _ = results
    h5a = rows(detail, "amended", "H5a", "overall", "scripted-signal").iloc[0]
    assert not h5a["estimable"] and "fewer than 16" in h5a["note"]   # 12 items per cell in this design
    from fplp.analysis.hypotheses import _item_wilson

    assert _item_wilson(pd.Series([0.0] * 16), pd.Series(range(16)))["hi"] < 0.20   # 16 is the minimum
    assert _item_wilson(pd.Series([0.0] * 15), pd.Series(range(15)))["hi"] >= 0.20


def test_registered_h5a_is_weighted_by_stratum_under_hand_labels():
    # Two strata of equal size in the registered population; the labeled sample has 3x as many warranted
    # answers. Warranted answers disclose, the others do not: the weighted rate is 0.5, the raw rate 0.75.
    df = pd.DataFrame([episode(i, "final_line", incomplete=1) for i in range(40)]
                      + [episode(100 + i, "final_line", signal="has_more", conflict="false_end", incomplete=1)
                         for i in range(40)])
    labeled = list(df.loc[df.conflict.isna(), "episode_id"][:30]) + list(df.loc[df.conflict.notna(), "episode_id"][:10])
    truth = df.set_index("episode_id")["conflict"].isna().astype(int)
    labels = pd.DataFrame({"episode_id": labeled, "label_a": truth[labeled].values, "label_b": truth[labeled].values,
                           "label": truth[labeled].values})
    df["disclosure_flag"] = 0   # the flag misses every disclosure: recall 0, so the hand labels are used
    detail, _ = run(df, n_boot=200, labels=labels, families=("registered",))
    h5a = rows(detail, "registered", "H5", "a").iloc[0]
    assert "weighted by stratum" in h5a["test"] and abs(h5a["diff"] - 0.5) < 1e-9


def test_h6_and_undocumented_verdicts_match_the_scripted_policies(results):
    detail, _ = results
    verdict = {(r.model, r.hypothesis): (r.supported, r.estimable)
               for r in detail[(detail.family == "amended") & (detail.part == "overall")].itertuples()}
    # H6: a signal reader sees the total (or the note) contradicting the false end and fetches; the
    # row counter already fetches under the false end alone (ceiling), so H6 is not estimable for it.
    assert verdict[("scripted-signal", "H6")] == (True, True) and verdict[("scripted-hybrid", "H6")] == (True, True)
    assert verdict[("scripted-if-full", "H6")][1] is False
    # Undocumented interface: the signal value still drives the signal readers, not the row counter.
    assert verdict[("scripted-signal", "A1u")] == (True, True) and verdict[("scripted-hybrid", "A1u")] == (True, True)
    assert verdict[("scripted-if-full", "A1u")] == (False, True)
    assert verdict[("scripted-signal", "H1u")] == (True, True)    # no-signal rate 0: room for H1a
    assert verdict[("scripted-hybrid", "H1u")][1] is False         # no-signal rate 100%: not estimable
    assert verdict[("scripted-hybrid", "H2u")] == (True, True) and verdict[("scripted-signal", "H2u")][1] is False


def test_retests_are_left_out_of_the_tests_and_measure_reliability(scored):
    from fplp.analysis.common import analysis_sample, retest_reliability

    assert (scored["arm"] == "retest").any()
    assert not (analysis_sample(scored)["arm"] == "retest").any()
    rel = retest_reliability(scored)
    assert set(rel["outcome"]) >= {"follow_up", "evidence_seen"}
    assert (rel["agreement"] == 1.0).all() and (rel["pairs"] > 0).all()   # scripted policies are deterministic


def test_missing_cells_are_named_as_the_reason_a_test_is_not_estimable(scored):
    # The pilot's situation: two main forms never run. The reason must name them, not the band.
    pilot_like = scored[~scored["signal_form"].isin(["total_count", "cursor_plus_note"])]
    detail, _ = run(pilot_like, n_boot=100, families=("registered", "amended"))
    for h in ("A1", "H1", "H2"):
        note = rows(detail, "amended", h, "overall", "scripted-signal")["note"].iloc[0]
        assert "no data for total_count, cursor_plus_note" in note and "%" not in note, (h, note)
    empty = rows(detail, "amended", "H1", "a", "scripted-signal")
    empty = empty[empty["test"].str.startswith("total_count")]
    assert empty["supported"].isna().all() and not empty["estimable"].any()   # no data: not estimable
    registered = rows(detail, "registered", "H1", "a", "scripted-signal")
    assert not registered[registered["test"].str.startswith("total_count")]["supported"].any()  # unchanged
    # with every cell present, the band is the reason
    note = rows(run(scored, n_boot=100, families=("amended",))[0], "amended", "H1", "overall", "scripted-if-full")["note"]
    assert note.iloc[0] == "a not estimable: no-signal rate above 90%"
