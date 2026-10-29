# Power

Simulated with `fplp power` on 20 Oct 2026 (amendment 1), for the pilot rule, H1a, and the amended A1, H1 and H2 (the other amended tests are not simulated). These numbers depend on assumed rates and variance; they are planning inputs, not results.

## What changed in amendment 1

The earlier simulation (19 Oct) gave "no signal" a different fetch rate on a real last page than when more rows exist. But with no signal, page 1 looks the same in both cases, so a model has one no-signal rate. The simulator now holds that rate equal on both extents (`fplp.analysis.simulate`), allows per-model rates, and can report the probability of each amended verdict. Earlier figures are in the git history.

## Setup

- Simulated scored episodes (`fplp simulate`): each form in three cells (needs-all tasks with more rows, page-1-sufficient tasks, a full last page), one run per item.
- Item difficulty varies (logit SD 1.0) and carries across forms; model offsets SD 0.3 (0 when rates are per model).

## Pilot rule (prereg section 6)

Two models, four forms, GO when one model has an RQ1 or RQ2 contrast with a Holm-corrected p below .05 and an observed difference of at least 15 points. 500 simulations per cell. No-signal rate 20% unless stated.

| True effect | 30 items per cell | 50 (planned) | 100 |
|---|---|---|---|
| none (every form at baseline): false GO | 0.014 | 0.024 | 0.024 |
| RQ1: explicit forms +15 points when more rows exist | 0.18 | 0.34 | 0.78 |
| RQ1: +25 points | 0.51 | 0.82 | 1.00 |
| RQ1 and RQ2: no-signal rate 50%, forms 75% when more rows exist and 25% on a last page | 0.71 | 0.96 | 1.00 |

## H1a in the main study

One model, six forms, 100 items per cell. H1a needs every explicit form to beat no signal (McNemar, Holm across five forms). Share of simulated models in which H1a is supported: 0.17, 0.46, 0.74 and 0.91 for a true effect of 15, 20, 25 and 30 points in every form (no-signal rate 20%). H1a can only be estimated for a model whose no-signal rate leaves room above it; amendment 1 marks it not estimable above 90%.

## Amended verdicts at rates read off the protocol checks

`docs/power-rates-checks.yaml` holds per-model rates read off the protocol checks (about 8 items per cell; forms the checks did not run set equal to `has_more`; an assumption, not a result). 200 simulations at 100 items per cell:

| Model | A1 (signal value) | H1 (amended) | H2 (amended) |
|---|---|---|---|
| claude-sonnet-5-5 | supported 1.00 | not estimable 1.00 | supported 1.00 |
| gpt-oss-120b | supported 1.00 | not supported 0.85, not estimable 0.15 | supported 1.00 |
| mistral-medium-3-5 | supported 1.00 | not estimable 1.00 | not supported 0.995 |

Under the final amended rules (a hypothesis with several parts is not estimable when a part is, unless an estimable part fails): H1 is not estimable for claude-sonnet-5-5 because its no-signal rate is at the ceiling (H1a), and for mistral-medium-3-5 because `total_count` already draws 98% fetching, leaving no room for the note to be higher (H1b). Only gpt-oss-120b is likely to be estimable, where the information-matched part fails (the note did slightly worse than `total_count` in the checks). **So the amended H1 verdict is expected to be "not estimable" overall;** A1 carries the claim that the signal's value drives fetching. H2 fails for mistral-medium-3-5 because its no-signal rate on a last page (27%) is close to its rate with the note (29%).

```sh
uv run fplp power --test amended --rates-file docs/power-rates-checks.yaml --items 100 --sims 200 \
  --forms none,has_more,next_cursor,total_count,nl_note_json,cursor_plus_note
uv run fplp power --items 30,50,100 --sims 500 \
  --rates "none=0.2/0.05/0.2,has_more=0.45/0.05/0.2,next_cursor=0.45/0.05/0.2,nl_note_json=0.45/0.05/0.2"
```

## What this means for the plan

1. **The pilot at 50 items** says GO 82% of the time for a true 25-point RQ1 effect and 96% when both contrasts move by 25 points, and 2.4% of the time without an effect. It is a feasibility check: a NO GO means "rescope", not "no effect".
2. **A1, the signal-value test, is well powered** wherever the checks suggest a signal effect, because its two sides differ by the signal's value and no ceiling or floor can decide it.
3. **H1a and H2a are informative only for models off the ceiling or floor.** At check-based rates, the amended H1 is expected to be not estimable overall (claude-sonnet-5-5 and mistral-medium-3-5). These are properties of the models and the documented interface, not of power.
