"""Simulate scored episodes with known effects, in the same columns `fplp score` writes.

Used to test the analysis scripts and to estimate power before real data exist. The default
rates are assumptions for simulation only; they are not results.

Cells: needs-all tasks with more rows (fetch needed), page-1-sufficient tasks with more rows, and
needs-all tasks on a full page that is the last one. The last two measure extra fetching.
Model: logit(p) = logit(rate[form, cell]) + u_item + v_model, with u_item shared across forms
(the payload is fixed per item, so item difficulty carries across forms).

With no signal, page 1 looks the same whether or not more rows exist, so the no-signal rate on a
full last page is set equal to its rate when more rows exist (amendment 1, issue 10); an assumed
rate that differs is ignored. Rates can differ by model (`rates_by_model`).

Usage: uv run fplp simulate --out data/processed/sim.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

# Assumed follow-up rates: (fetch needed, page-1-sufficient, full last page).
DEFAULT_RATES = {
    "none": (0.20, 0.05, 0.10),
    "has_more": (0.45, 0.10, 0.10),
    "next_cursor": (0.45, 0.10, 0.10),
    "total_count": (0.40, 0.08, 0.10),
    "link_header": (0.35, 0.08, 0.10),
    "page_info": (0.45, 0.10, 0.10),
    "nl_note": (0.60, 0.20, 0.15),
    "nl_note_json": (0.60, 0.20, 0.15),
    "placeholder_row": (0.60, 0.20, 0.10),
    "cursor_plus_note": (0.65, 0.15, 0.10),
}
TASKS = {"needs_all": ["filtered_count", "oldest_date", "exists", "export_all"], "page1_sufficient": ["name_one", "lookup"]}
CELLS = [("needs_all", "more_full", 0), ("page1_sufficient", "more_full", 1), ("needs_all", "last_full", 2)]


def parse_rates(spec: str | None) -> dict[str, tuple[float, float, float]]:
    """Parse "form=needed[/page1[/last_full]],..." overrides on top of DEFAULT_RATES."""
    rates = dict(DEFAULT_RATES)
    for part in filter(None, (spec or "").split(",")):
        form, value = part.split("=")
        old = rates.get(form, (0.0, 0.1, 0.1))
        given = [float(v) for v in value.split("/")]
        rates[form] = tuple(given + list(old[len(given):]))
    return rates


def _logit(p: float) -> float:
    return float(np.log(p / (1 - p)))


def simulate(
    forms: list[str],
    models: list[str],
    items_per_cell: int,
    rates: dict[str, tuple[float, float, float]] | None = None,
    item_sd: float = 1.0,
    model_sd: float = 0.3,
    seed: int = 0,
    rates_by_model: dict[str, dict[str, tuple[float, float, float]]] | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for model in models:
        model_rates = dict((rates_by_model or {}).get(model) or rates or DEFAULT_RATES)
        if "none" in model_rates:  # the no-signal pages look the same: one rate for both extents
            needed_rate, page1_rate, _ = model_rates["none"]
            model_rates["none"] = (needed_rate, page1_rate, needed_rate)
        v = rng.normal(0, model_sd)
        for need, extent, idx in CELLS:
            tasks = TASKS[need]
            needed = idx == 0
            u = rng.normal(0, item_sd, items_per_cell)  # one draw per item, shared across forms
            for form in forms:
                base = _logit(min(0.98, max(0.02, model_rates[form][idx])))
                p = 1 / (1 + np.exp(-(base + u + v)))
                fetched = rng.random(items_per_cell) < p
                for item in range(items_per_cell):
                    f = int(fetched[item])
                    complete = f if needed else 1
                    rows.append({
                        "episode_id": f"sim-{model}-{form}-{need}-{extent}-{item}",
                        "model": model,
                        "arm": "core",
                        "signal_form": form,
                        "extent": extent,
                        "task_need": need,
                        "task_type": tasks[item % len(tasks)],
                        "item": item,
                        "replicate": 0,
                        "fetch_needed": int(needed),
                        "follow_up": f,
                        "missed_fetch": 1 - f if needed else None,
                        "extra_fetch": None if needed else f,
                        "completion": complete,
                        "correct": complete,
                        "justified_correct": complete,
                        "disclosed": None if complete else int(rng.random() < 0.2),
                        "hedged": int(rng.random() < 0.05) if complete else None,
                    })
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--forms", default=",".join(DEFAULT_RATES))
    parser.add_argument("--models", default="model-a,model-b,model-c")
    parser.add_argument("--items-per-cell", type=int, default=50)
    parser.add_argument("--rates", help='overrides, e.g. "none=0.2/0.05/0.1,nl_note_json=0.5"')
    parser.add_argument("--item-sd", type=float, default=1.0)
    parser.add_argument("--model-sd", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    df = simulate(args.forms.split(","), args.models.split(","), args.items_per_cell,
                  parse_rates(args.rates), args.item_sd, args.model_sd, args.seed)
    df.to_csv(args.out, index=False)
    print(f"{len(df)} simulated episodes -> {args.out}")


if __name__ == "__main__":
    main()
