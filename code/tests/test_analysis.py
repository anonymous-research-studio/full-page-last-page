"""The analysis commands run on simulated data and recover a known effect."""

from pathlib import Path

import pandas as pd

from fplp.analysis import disclosure, figure, go_no_go, model, power, rates
from fplp.analysis.common import agresti_min, holm, paired, sign_flip_p
from fplp.analysis.go_no_go import preregistered_decision
from fplp.analysis.simulate import parse_rates, simulate

FORMS = ["none", "has_more", "next_cursor", "nl_note_json"]


def test_go_no_go_detects_large_effect_and_ignores_null():
    big = parse_rates("none=0.1/0.05/0.6,has_more=0.6/0.1/0.1,next_cursor=0.6/0.1/0.1,nl_note_json=0.6/0.1/0.1")
    assert preregistered_decision(simulate(FORMS, ["a", "b"], 80, big, seed=1), n_boot=300)["go"]

    null = parse_rates("none=0.3/0.1/0.3,has_more=0.3/0.1/0.3,next_cursor=0.3/0.1/0.3,nl_note_json=0.3/0.1/0.3")
    assert not preregistered_decision(simulate(FORMS, ["a", "b"], 80, null, seed=1), n_boot=300)["go"]


def test_paired_tests():
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    keys = [f"t:{i}" for i in range(40)]
    a = pd.DataFrame({"key": keys, "v": [1] * 30 + [0] * 10})
    b = pd.DataFrame({"key": keys, "v": [0] * 25 + [1] * 5 + [0] * 10})
    t = paired(a, b, "v", rng)
    assert t["method"].startswith("McNemar") and t["diff"] == 0.625 and t["p"] < 0.001 and t["lo"] > 0.4
    # Replicates average within an item, so the sign-flip test is used and items are not inflated.
    reps = pd.concat([a.assign(v=a["v"] * r) for r in (0, 1, 1)])
    assert paired(reps, b, "v", rng)["method"].startswith("sign-flip") and paired(reps, b, "v", rng)["n"] == 40
    assert sign_flip_p(np.zeros(10), rng, 1000) == 1.0
    lo, hi = agresti_min(0, 0, 50, 0.95)
    assert lo < 0 < hi and abs(lo + hi) < 1e-12
    assert holm([0.01, 0.04, 0.03]) == [True, False, False] and holm([0.01, float("nan")]) == [True, False]


def test_commands_run_end_to_end(tmp_path):
    sim = tmp_path / "sim.csv"
    simulate([*FORMS, "cursor_plus_note"], ["a", "b", "c"], 30, seed=2).to_csv(sim, index=False)
    rates.main([str(sim), "--out", str(tmp_path / "rates.csv"), "--n-boot", "200"])
    go_no_go.main([str(sim), "--n-boot", "200", "--out", str(tmp_path / "gng.csv"), "--config", "none"])
    model.main([str(sim), "--spec", "fixed", "--out", str(tmp_path / "fixed.csv")])
    model.main([str(sim), "--spec", "mixed", "--out", str(tmp_path / "mixed.csv")])
    figure.main([str(sim), "--out", str(tmp_path / "fig"), "--n-boot", "200"])
    assert (tmp_path / "fig.pdf").exists() and (tmp_path / "fig.png").exists()
    coef = pd.read_csv(tmp_path / "fixed.csv")
    main_effect = coef.loc[coef["term"].str.endswith("[T.nl_note_json]"), "estimate"]
    assert len(main_effect) == 1 and main_effect.iloc[0] > 0


def test_power_runs(capsys):
    power.main(["--items", "20", "--sims", "3", "--n-boot", "50"])
    assert "items_per_cell" in capsys.readouterr().out


def test_disclosure_sample_and_check(tmp_path, capsys):
    import yaml

    from fplp import cli

    cfg = tmp_path / "d.yaml"
    cfg.write_text(yaml.safe_dump({
        "name": "d", "models": ["scripted-never", "scripted-follow"], "signal_forms": ["none"],
        "task_need": ["needs_all"], "items_per_cell": 30,
        "arms": {"conflict": {"levels": ["false_end"], "task_need": ["needs_all"],
                              "answer_formats": ["final_line", "completeness"]}}}))
    models = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env")])
    raw = str(tmp_path / "raw" / "d")
    plan = ["--config", str(cfg), "--models-file", str(models)]
    to_label = tmp_path / "to_label.csv"
    disclosure.main(["sample", raw, "--incomplete", "10", "--complete", "10", "--pairs-warranted", "0",
                     "--pairs-false", "4", "--overlap", "8", "--out", str(to_label), *plan])
    sample = pd.read_csv(to_label)
    second = pd.read_csv(tmp_path / "to_label_second.csv")
    assert list(sample.columns) == ["episode_id", "question", "reply", "label"]
    assert 20 < len(sample) <= 28                       # validation strata plus both members of each pair
    assert not sample["reply"].str.contains("COMPLETENESS").any()   # labelers judge the prose only
    assert len(second) == 8 and set(second["episode_id"]) <= set(sample["episode_id"])   # the overlap

    a, b = sample.assign(label=0), second.assign(label=0)
    b.loc[b.index[0], "label"] = 1  # one disagreement on the overlap, left unresolved
    a.to_csv(tmp_path / "a.csv", index=False)
    b.to_csv(tmp_path / "b.csv", index=False)
    out = tmp_path / "labels.csv"
    disclosure.main(["check", str(tmp_path / "a.csv"), str(tmp_path / "b.csv"), raw, "--out", str(out), *plan])
    printed = capsys.readouterr().out
    assert f"{len(sample)} replies labeled; 8 by both authors" in printed
    assert "1 disagreement(s) not yet adjudicated" in printed
    labels = pd.read_csv(out)
    assert len(labels) == len(sample) and labels["label"].isna().sum() == 1   # outside the overlap: first author


def test_disclosure_sample_oversamples_warranted_answers(tmp_path):
    import yaml

    from fplp import cli
    from fplp.analysis.disclosure import draw, load_scored

    cfg = tmp_path / "s.yaml"
    cfg.write_text(yaml.safe_dump({
        "name": "s", "models": ["scripted-never"], "signal_forms": ["none"], "extents": ["more_full", "more_short"],
        "task_need": ["needs_all"], "items_per_cell": 30,
        "arms": {"conflict": {"levels": ["false_end"], "task_need": ["needs_all"]}}}))
    models = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(tmp_path / "raw"),
              "--env-file", str(tmp_path / "none.env")])
    scored = load_scored(str(tmp_path / "raw" / "s"), str(cfg), str(models))
    sample = draw(scored, n_incomplete=20, n_complete=0, pairs_warranted=0, pairs_false=0, seed=1)
    strata = sample["disclosure_stratum"].value_counts().to_dict()
    assert strata["warranted"] == 14 and sum(strata.values()) == 20   # 70% from the warranted stratum
    assert set(strata) <= {"warranted", "short_page", "api_said_done"}


def test_rates_reads_files_scored_before_the_rename(tmp_path):
    sim = simulate(FORMS, ["a"], 10, seed=3).rename(columns={"extra_fetch": "unnecessary_fetch"})
    sim.to_csv(tmp_path / "old.csv", index=False)
    rates.main([str(tmp_path / "old.csv"), "--out", str(tmp_path / "r.csv"), "--n-boot", "50"])
    assert "extra_fetch" in set(pd.read_csv(tmp_path / "r.csv")["metric"])


def test_warranted_pairs_are_drawn_where_the_answers_can_differ():
    """H5b(a)'s labeled pairs come from pairs with an incomplete answer in either format: pairs where both
    answers are complete differ by zero (changelog, 23 Oct 2026)."""
    from fplp.analysis.disclosure import draw

    rows = [{"episode_id": f"{fmt}-{i}", "model": "m", "task_need": "needs_all", "empty_reply": 0,
             "stop_reason": "end_turn", "answer_format": fmt, "evidence_seen": 0 if i < 10 and fmt == "final_line" else 1,
             "disclosure_stratum": None, "arm": "core", "key": f"t:{i}", "signal_form": "none", "conflict": None,
             "extent": "more_full", "task_type": "t", "item": i, "replicate": 0}
            for i in range(40) for fmt in ("final_line", "completeness")]
    sample = draw(pd.DataFrame(rows), n_incomplete=0, n_complete=0, pairs_warranted=20, pairs_false=0, seed=0)
    assert set(sample["item"]) == set(range(10)) and len(sample) == 20   # only the ten pairs that can differ


def test_labeling_sample_never_draws_retests(tmp_path):
    from fplp.analysis.disclosure import draw

    rows = [{"episode_id": f"e{i}", "model": "m", "task_need": "needs_all", "empty_reply": 0, "stop_reason": "end_turn",
             "answer_format": "final_line", "evidence_seen": 0, "disclosure_stratum": "warranted",
             "arm": "retest" if i % 2 else "core", "key": f"t:{i}", "signal_form": "none", "conflict": None,
             "extent": "more_full", "task_type": "t", "item": i, "replicate": i % 2, "question": "q", "reply": "r"}
            for i in range(40)]
    sample = draw(pd.DataFrame(rows), n_incomplete=30, n_complete=0, pairs_warranted=0, pairs_false=0, seed=0)
    assert not (sample["arm"] == "retest").any() and len(sample) == 20
