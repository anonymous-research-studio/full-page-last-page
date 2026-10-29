"""Write the paper's results tables (LaTeX rows) and headline figure from the analysis output, so no
number in the paper is copied by hand.

Inputs: the per-test CSV from `fplp hypotheses --out` (and its `_retest.csv` beside it), and the
scored CSV the tests were run on. Each table's rows go to their own file in --out-dir; the manuscript
reads them with \\IfFileExists and shows a placeholder until they exist. Columns follow the model
order of --config (the pre-registered confirmatory set by default).

  h1_rows.tex           fetch when needed: no-signal rate, each main form minus no signal (H1a), and
                        the information-matched pair (H1b, 90% CI)
  a1_rows.tex           signal value (A1): fetch when more rows exist minus on a real last page, per
                        main form, the no-signal reference, and the undocumented forms (A1u)
  rq3_rows.tex          fetch where the row count and a truthful signal disagree (H3), with the
                        row-count-use gate
  false_rows.tex        fetch under each false signal against no signal, the same form's truthful
                        signal and a real last page ("a / b / c" in model order)
  verdict_rows.tex      registered and amended verdicts per model, with the overall verdict ("pending"
                        while a model in --config has no tests yet: the rule needs every model)
  reliability_rows.tex  retest agreement and Cohen's kappa per model
  calibration.pdf       the headline figure, one panel per model (`fplp figure --facet-models`)
  pilot_rows.tex        with --pilot: the go/no-go contrasts and per-model health from `fplp go-no-go
                        --out` (a feasibility check, reported apart from the results)
  provenance.json       the commit and the SHA-256 of every input (`fplp stamp`); pilot_provenance.json
                        for --pilot alone

Differences are in percentage points with 95% CIs (H1b: 90%); bold marks a contrast significant
after Holm's correction within its part, in either direction.

Usage: uv run fplp tables results/tables/main_hypotheses.csv data/processed/main.csv --out-dir results/tex
       uv run fplp tables --pilot results/tables/pilot_go_no_go.csv --out-dir results/tex
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from fplp.analysis.common import MODEL_NAMES, analysis_sample, holm
from fplp.analysis.hypotheses import (
    FALSE_END,
    MAIN_EXPLICIT,
    UNDOCUMENTED_FORMS,
    VISIBLE,
    _cells,
    _item_wilson,
    _overall,
    confirmatory_models,
)

FORM_NAMES = {"none": "No signal", "has_more": r"\code{has\_more}", "next_cursor": r"\code{next\_cursor}",
              "total_count": r"\code{total\_count}", "nl_note_json": "NL note (JSON)",
              "cursor_plus_note": "Cursor + note"}
FALSE_NAMES = {"false_end": r"\code{has\_more: false}", "false_end_cursor": r"\code{next\_cursor: null}",
               "false_total": r"\code{total\_count} = rows shown", "false_note": r"Note ``1--20 of 20''",
               "visible_conflict_total": r"\code{has\_more: false} + total 87 (H6)",
               "visible_conflict_note": r"Null cursor + ``1--20 of 87'' (H6)"}
AMENDED = ["A1", "H1", "H2", "H2b", "H3", "H3r", "H4", "H5a", "H5b", "H6", "A1u", "H1u", "H2u"]
REGISTERED = ["H1", "H2", "H3", "H4", "H5"]


def _pp(diff: float, lo: float, hi: float, bold: bool = False) -> str:
    """A difference in percentage points with its CI, e.g. +42 [31, 53]."""
    if not np.isfinite(diff):
        return "--"
    cell = f"{100 * diff:+.0f} [{100 * lo:+.0f}, {100 * hi:+.0f}]"
    return rf"\textbf{{{cell}}}" if bold else cell


def _rate(diff: float, lo: float, hi: float) -> str:
    """A rate in percent with its CI, e.g. 64 [52, 75]."""
    return "--" if not np.isfinite(diff) else f"{100 * diff:.0f} [{100 * lo:.0f}, {100 * hi:.0f}]"


def _pct(x: float) -> str:
    return "--" if not np.isfinite(x) else f"{100 * x:.0f}"


def _row(label: str, cells: list[str]) -> str:
    return " & ".join([label, *cells]) + r" \\"


def _tests(detail: pd.DataFrame, model: str, h: str, part: str) -> pd.DataFrame:
    """One part's rows for one model, with Holm's correction recomputed across them."""
    rows = detail[(detail.model == model) & (detail.family == "amended") & (detail.hypothesis == h)
                  & (detail.part == part)].copy()
    rows["holm"] = holm(rows["p"].tolist()) if len(rows) else []
    return rows


def _cell(rows: pd.DataFrame, prefix: str, holm_bold: bool = True) -> str:
    r = rows[rows["test"].str.startswith(prefix)]
    if r.empty:
        return "--"
    r = r.iloc[0]
    return _pp(r["diff"], r["lo"], r["hi"], bold=holm_bold and bool(r.get("holm", False)))


def _sample(scored: pd.DataFrame) -> dict[str, dict]:
    """The cells the amended tests use, per model, from the same filters as `fplp hypotheses`."""
    return {m: _cells(g, own_small_page=True) for m, g in analysis_sample(scored).groupby("model")}


def h1_rows(detail: pd.DataFrame, scored: pd.DataFrame, models: list[str]) -> str:
    cells = _sample(scored)

    def base_rate(m: str) -> str:
        if m not in cells:
            return "--"
        none = cells[m]["need"][cells[m]["need"].signal_form == "none"]
        r = _item_wilson(none["follow_up"], none["key"])
        return _rate(r["diff"], r["lo"], r["hi"])

    lines = [_row("No signal (rate, \\%)", [base_rate(m) for m in models])]
    parts = {m: _tests(detail, m, "H1", "a") for m in models}
    lines += [_row(f"{FORM_NAMES[f]} $-$ none", [_cell(parts[m], f"{f} - none") for m in models]) for f in MAIN_EXPLICIT]
    lines.append(r"\midrule")
    lines.append(_row(r"NL note $-$ \code{total\_count} (H1b)",
                      [_cell(_tests(detail, m, "H1", "b (information-matched)"), "nl_note_json", holm_bold=False)
                       for m in models]))
    return "\n".join(lines) + "\n"


def a1_rows(detail: pd.DataFrame, models: list[str]) -> str:
    parts = {m: _tests(detail, m, "A1", "a") for m in models}
    lines = [_row(FORM_NAMES[f], [_cell(parts[m], f"{f}:") for m in models]) for f in MAIN_EXPLICIT]
    lines.append(_row("No signal (reference)", [_cell(_tests(detail, m, "A1", "reference"), "none:", holm_bold=False)
                                                for m in models]))
    lines.append(r"\midrule")
    undoc = {m: _tests(detail, m, "A1u", "a") for m in models}
    lines += [_row(f"{FORM_NAMES[f]}, undocumented", [_cell(undoc[m], f"{f}, undocumented") for m in models])
              for f in UNDOCUMENTED_FORMS]
    return "\n".join(lines) + "\n"


def rq3_rows(detail: pd.DataFrame, models: list[str]) -> str:
    def rate(m: str, part: str) -> str:
        r = _tests(detail, m, "H3", part)
        return _rate(*r[["diff", "lo", "hi"]].iloc[0]) if len(r) else "--"

    lines = [_row(r"Full last page (rows: more; signal: done)", [rate(m, "a") for m in models]),
             _row(r"Short first page (rows: done; signal: more)", [rate(m, "b") for m in models]),
             r"\midrule",
             _row(r"No signal: full $-$ short first page (pp)",
                  [_cell(_tests(detail, m, "H3", "context: row-count use"), "no signal", holm_bold=False) for m in models])]
    return "\n".join(lines) + "\n"


def false_rows(scored: pd.DataFrame, models: list[str]) -> str:
    cells = _sample(scored)

    def rates(pick) -> str:
        return " / ".join(_pct(pick(cells[m])["follow_up"].mean()) if m in cells and len(pick(cells[m])) else "--"
                          for m in models)

    lines = []
    for cf in [*FALSE_END, *VISIBLE]:
        form = FALSE_END.get(cf) or FALSE_END[VISIBLE[cf]]
        if cf == next(iter(VISIBLE)):
            lines.append(r"\midrule")
        lines.append(_row(FALSE_NAMES[cf], [
            rates(lambda c, cf=cf: c["conflicts"][c["conflicts"]["conflict"] == cf]),
            rates(lambda c: c["need"][c["need"].signal_form == "none"]),
            rates(lambda c, form=form: c["need"][c["need"].signal_form == form]),
            "--" if cf in VISIBLE else rates(lambda c, form=form: c["last"][c["last"].signal_form == form])]))
    return "\n".join(lines) + "\n"


def _verdict(supported, estimable) -> str:
    if estimable is False or (isinstance(estimable, float) and np.isnan(estimable)) or not bool(estimable):
        return "n.e."
    return "yes" if supported is True or supported == 1.0 else "no"


def verdict_rows(detail: pd.DataFrame, models: list[str]) -> str:
    # The overall rules count every confirmatory model, so with one still to run there is no verdict yet.
    pending = any(m not in set(detail["model"]) for m in models)
    lines = []
    for family, hyps in (("amended", AMENDED), ("registered", REGISTERED)):
        fam = detail[(detail.family == family) & (detail.part == "overall")]
        if fam.empty:
            continue
        overall = _overall(detail, family, models)
        if lines:
            lines.append(r"\midrule")
        for h in hyps:
            rows = fam[fam.hypothesis == h]
            if rows.empty:
                continue
            cells = []
            for m in models:
                r = rows[rows.model == m]
                # The registered family has no estimability rule: a model either supports it or not.
                est = r["estimable"].iloc[0] if family == "amended" and len(r) else True
                cells.append(_verdict(r["supported"].iloc[0], est) if len(r) else "--")
            total = overall.loc[h, "supported_overall"] if h in overall.index else "--"
            total = "pending" if pending else {True: "yes", False: "no", "not estimable": "n.e."}.get(total, str(total))
            label = h + (" (reg.)" if family == "registered" else "")
            lines.append(_row(label, [*cells, rf"\textbf{{{total}}}"]))
    return "\n".join(lines) + "\n"


def reliability_rows(reliability: pd.DataFrame, models: list[str]) -> str:
    lines = []
    for m in models:
        r = reliability[reliability.model == m].set_index("outcome")
        if r.empty:
            lines.append(_row(MODEL_NAMES.get(m, m), ["--"] * 4))
            continue

        def cell(outcome: str, r=r) -> str:
            if outcome not in r.index:
                return "--"
            k = r.loc[outcome, "kappa"]
            return rf"{100 * r.loc[outcome, 'agreement']:.0f}\% ({'--' if not np.isfinite(k) else f'{k:.2f}'})"

        lines.append(_row(MODEL_NAMES.get(m, m), [str(int(r["pairs"].iloc[0])), cell("follow_up"),
                                                  cell("evidence_seen"), cell("correct")]))
    return "\n".join(lines) + "\n"


def pilot_rows(contrasts: pd.DataFrame, health: pd.DataFrame, models: list[str]) -> str:
    """Go/no-go contrasts per model under a line giving the model's no-signal rate and empty replies."""
    lines = []
    for m in [m for m in models if m in set(health["model"])]:
        h = health.set_index("model").loc[m]
        base = h["no_signal_rate_when_needed"]
        counted = "" if 0.10 <= base <= 0.90 else " (RQ1 not counted)"
        if lines:
            lines.append(r"\midrule")
        lines.append(rf"\multicolumn{{3}}{{p{{0.9\linewidth}}}}{{\emph{{{MODEL_NAMES.get(m, m)}: no signal when needed {_pct(base)}\%"
                     rf"{counted}; empty replies {_pct(h['empty_reply_rate'])}\%}}}} \\")
        for _, r in contrasts[contrasts["model"] == m].iterrows():
            a, b = r["contrast"].split(" - ")
            label = f"{r['rq']}: {FORM_NAMES.get(a, a)} $-$ {FORM_NAMES.get(b, b).lower() if b == 'none' else FORM_NAMES.get(b, b)}"
            lines.append(_row(label, [_pp(r["diff"], r["lo"], r["hi"]), "yes" if bool(r["passes"]) else "no"]))
    return "\n".join(lines) + "\n"


def write_tables(detail: pd.DataFrame, scored: pd.DataFrame, models: list[str], out_dir: Path,
                 reliability: pd.DataFrame | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {"h1_rows.tex": h1_rows(detail, scored, models), "a1_rows.tex": a1_rows(detail, models),
             "rq3_rows.tex": rq3_rows(detail, models), "false_rows.tex": false_rows(scored, models),
             "verdict_rows.tex": verdict_rows(detail, models)}
    if reliability is not None and len(reliability):
        files["reliability_rows.tex"] = reliability_rows(reliability, models)
    for name, text in files.items():
        (out_dir / name).write_text(text)
    return [out_dir / name for name in files]


def read_detail(path: str | Path) -> pd.DataFrame:
    """The per-test CSV, with supported/estimable restored to True, False or None."""
    detail = pd.read_csv(path)
    for name in ("supported", "estimable"):
        detail[name] = detail[name].map({"True": True, "False": False, True: True, False: False}).astype(object)
        detail[name] = detail[name].where(detail[name].notna(), None)
    return detail


def read_reliability(hypotheses_csv: str | Path) -> pd.DataFrame | None:
    hyp = Path(hypotheses_csv)
    path = hyp.with_name(f"{hyp.stem}_retest{hyp.suffix}")
    try:
        return pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hypotheses_csv", nargs="?", help="per-test CSV written by `fplp hypotheses --out`")
    parser.add_argument("scored_csv", nargs="?", help="the scored CSV the tests were run on")
    parser.add_argument("--pilot", help="go/no-go CSV from `fplp go-no-go --out` (its _models.csv beside it)")
    parser.add_argument("--out-dir", default="results/tex")
    parser.add_argument("--config", default="configs/runs/main.yaml",
                        help="run config whose models give the column order (default: the main study)")
    parser.add_argument("--no-figure", action="store_true")
    parser.add_argument("--width", type=float, default=7.0, help="figure width in inches (ACM full width is 7)")
    parser.add_argument("--n-boot", type=int, default=2000)
    args = parser.parse_args(argv)

    if not (args.hypotheses_csv or args.pilot):
        parser.error("give the hypotheses and scored CSVs, --pilot, or both")
    if bool(args.hypotheses_csv) != bool(args.scored_csv):
        parser.error("the hypotheses CSV and the scored CSV go together")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    models = confirmatory_models(args.config) or []
    if args.pilot:
        pilot = Path(args.pilot)
        contrasts = pd.read_csv(pilot)
        health = pd.read_csv(pilot.with_name(f"{pilot.stem}_models{pilot.suffix}"))
        order = [m for m in models if m in set(health["model"])] + sorted(set(health["model"]) - set(models))
        (out_dir / "pilot_rows.tex").write_text(pilot_rows(contrasts, health, order))
        print(f"wrote {out_dir / 'pilot_rows.tex'}")
    if not args.hypotheses_csv:
        _stamp(out_dir, [pilot, pilot.with_name(f"{pilot.stem}_models{pilot.suffix}")], "pilot_provenance.json")
        return
    detail = read_detail(args.hypotheses_csv)
    scored = pd.read_csv(args.scored_csv)
    models = models or sorted(detail["model"].unique())
    missing = [m for m in models if m not in set(detail["model"])]
    if missing:
        print(f"warning: no tests for {', '.join(missing)}; their columns show --")
    written = write_tables(detail, scored, models, out_dir, read_reliability(args.hypotheses_csv))
    for path in written:
        print(f"wrote {path}")
    if not args.no_figure:
        from fplp.analysis import figure

        figure.main([args.scored_csv, "--out", str(out_dir / "calibration"), "--facet-models",
                     "--models", ",".join(models), "--width", str(args.width), "--n-boot", str(args.n_boot)])
    hyp = Path(args.hypotheses_csv)
    _stamp(out_dir, [hyp, hyp.with_name(f"{hyp.stem}_retest{hyp.suffix}"), Path(args.scored_csv)], "provenance.json")


def _stamp(out_dir: Path, inputs: list[Path], name: str) -> None:
    """Record the commit and the checksums of the inputs beside the tables (`fplp stamp`)."""
    from fplp.provenance import write_stamp

    write_stamp(out_dir / name, [p for p in inputs if p.exists()])


if __name__ == "__main__":
    main()
