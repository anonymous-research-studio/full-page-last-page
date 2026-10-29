"""The paper's tables come from the analysis output unchanged: verdicts match `fplp hypotheses`, a CSV
round trip changes nothing, and the cells read the right rows."""

import json
from pathlib import Path

import pandas as pd
import pytest
from test_hypotheses import CONFIG

from fplp import cli
from fplp.analysis.common import retest_reliability
from fplp.analysis.hypotheses import run
from fplp.analysis.tables import read_detail, verdict_rows, write_tables

MODELS = ["scripted-signal", "scripted-if-full", "scripted-hybrid"]


@pytest.fixture(scope="module")
def scored_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("tables")
    cfg = root / "tab.yaml"
    cfg.write_text(CONFIG.replace("name: hyp", "name: tab"))
    models = Path(__file__).resolve().parents[1] / "configs" / "models.yaml"
    cli.main(["run", str(cfg), "--models-file", str(models), "--out-dir", str(root / "raw"),
              "--env-file", str(root / "none.env"), "--workers", "8"])
    cli.main(["score", str(root / "raw" / "tab"), "--out", str(root / "scored.csv")])
    return root / "scored.csv"


@pytest.fixture(scope="module")
def tables(scored_path, tmp_path_factory):
    scored = pd.read_csv(scored_path)
    detail, overall = run(scored, n_boot=200, confirmatory=MODELS)
    out = tmp_path_factory.mktemp("tex")
    write_tables(detail, scored, MODELS, out, retest_reliability(scored))
    return detail, overall, out


def cells(text: str, label: str) -> list[str]:
    """The cells of the row whose label starts with `label`."""
    line = next(row for row in text.splitlines() if row.startswith(label))
    return [c.strip() for c in line.removesuffix(r"\\").split("&")][1:]


def test_every_table_is_written(tables):
    _, _, out = tables
    names = {p.name for p in out.iterdir()}
    assert names == {"h1_rows.tex", "a1_rows.tex", "rq3_rows.tex", "false_rows.tex", "verdict_rows.tex",
                     "reliability_rows.tex"}
    columns = {"h1_rows.tex": 3, "a1_rows.tex": 3, "rq3_rows.tex": 3, "false_rows.tex": 4, "verdict_rows.tex": 4,
               "reliability_rows.tex": 4}
    for name, n in columns.items():
        for row in (out / name).read_text().splitlines():
            assert row == r"\midrule" or (row.count("&") == n and row.endswith(r"\\")), (name, row)


def test_overall_verdicts_match_the_hypotheses_command(tables):
    _, overall, out = tables
    text = (out / "verdict_rows.tex").read_text()
    show = {True: "yes", False: "no", "not estimable": "n.e."}
    for h, v in overall["amended"]["supported_overall"].items():
        assert cells(text, f"{h} &")[-1] == rf"\textbf{{{show[v]}}}", h
    for h, v in overall["registered"]["supported_overall"].items():
        assert cells(text, f"{h} (reg.)")[-1] == rf"\textbf{{{show[v]}}}", h


def test_per_model_verdicts_follow_the_policies(tables):
    _, _, out = tables
    text = (out / "verdict_rows.tex").read_text()
    assert cells(text, "A1 &")[:3] == ["yes", "no", "yes"]        # the signal's value drives the signal followers
    assert cells(text, "H3 &")[:3] == ["n.e.", "yes", "no"]       # gated on row-count use
    assert cells(text, "H1 (reg.)")[0] in {"yes", "no"}          # registered verdicts are never "n.e."


def test_bold_marks_holm_significant_contrasts(tables):
    _, _, out = tables
    h1 = (out / "h1_rows.tex").read_text()
    signal, if_full, hybrid = cells(h1, r"\code{has\_more} $-$ none")
    assert signal.startswith(r"\textbf{+100") and not if_full.startswith(r"\textbf") and not hybrid.startswith(r"\textbf")
    assert cells(h1, "No signal (rate")[0].startswith("0 [")       # the signal follower never fetches without one
    a1 = (out / "a1_rows.tex").read_text()
    assert all(c.startswith("+0 [") and r"\textbf" not in c for c in cells(a1, "No signal (reference)"))


def test_false_signal_rows_compare_the_same_rows(tables):
    _, _, out = tables
    text = (out / "false_rows.tex").read_text()
    false, none, truthful, last = cells(text, r"\code{has\_more: false}")
    # signal follower / row counter / hybrid: the false end stops the followers, not the row counter
    assert false == "0 / 100 / 0" and none == "0 / 100 / 100" and truthful == "100 / 100 / 100" and last == "0 / 100 / 0"
    assert cells(text, r"\code{has\_more: false} + total 87")[-1] == "--"


def test_csv_round_trip_and_cli(tables, scored_path, tmp_path):
    detail, _, out = tables
    csv = tmp_path / "h.csv"
    detail.to_csv(csv, index=False)
    retest_reliability(pd.read_csv(scored_path)).to_csv(tmp_path / "h_retest.csv", index=False)
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(CONFIG)
    cli.main(["tables", str(csv), str(scored_path), "--out-dir", str(tmp_path / "tex"), "--config", str(cfg),
              "--n-boot", "50"])
    for p in out.iterdir():
        assert (tmp_path / "tex" / p.name).read_text() == p.read_text(), p.name
    assert (tmp_path / "tex" / "calibration.pdf").stat().st_size > 0
    assert read_detail(csv)["supported"].map(type).isin([bool, type(None)]).all()
    stamp = json.loads((tmp_path / "tex" / "provenance.json").read_text())
    assert set(stamp["inputs"]) == {str(csv), str(tmp_path / "h_retest.csv"), str(scored_path)}


def test_a_model_without_tests_shows_dashes_and_no_overall_verdict(tables):
    detail, _, _ = tables
    text = verdict_rows(detail, [*MODELS, "absent-model"])
    assert all(cells(text, f"{h} &")[3] == "--" for h in ["A1", "H4"])
    assert all(row.endswith(r"\textbf{pending} \\") for row in text.splitlines() if row != r"\midrule")


def test_pilot_table_from_the_go_no_go_output(scored_path, tmp_path):
    from fplp.analysis.go_no_go import main as go_no_go

    pilot = tmp_path / "go.csv"
    go_no_go([str(scored_path), "--config", "none", "--out", str(pilot), "--n-boot", "50"])
    assert (tmp_path / "go_models.csv").exists()
    cli.main(["tables", "--pilot", str(pilot), "--out-dir", str(tmp_path / "tex"), "--config", "none"])
    text = (tmp_path / "tex" / "pilot_rows.tex").read_text()
    contrasts = pd.read_csv(pilot)
    rows = [r for r in text.splitlines() if r.startswith("RQ")]
    assert len(rows) == len(contrasts) and all(r.count("&") == 2 for r in rows)
    assert text.count(r"\multicolumn") == pd.read_csv(tmp_path / "go_models.csv")["model"].nunique()
    assert not (tmp_path / "tex" / "verdict_rows.tex").exists()   # the pilot alone writes no results table


def test_tables_needs_inputs(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["tables", "--out-dir", str(tmp_path)])
