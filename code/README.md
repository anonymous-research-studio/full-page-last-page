# Full Page ≠ Last Page

Which completeness signals in Web API responses do LLM agents act on? A controlled study that holds the returned rows fixed and varies only how a paginated API signals that more results exist, crossed with whether the first page is full and whether more rows actually exist.

## Status

As of 23 Oct 2026, before the remaining runs. Every run listed below as pending has since been completed; the artifact's top-level README describes the released state.

- The design, hypotheses and analysis are fixed in [prereg/PREREGISTRATION.md](prereg/PREREGISTRATION.md) (registered 19 Oct), amended before the pilot by [prereg/AMENDMENT-1.md](prereg/AMENDMENT-1.md) and, with exploratory checks only, by [prereg/AMENDMENT-2.md](prereg/AMENDMENT-2.md). See [prereg/README.md](prereg/README.md).
- Protocol checks (19 Oct, 768 episodes, not results): [data/protocol-checks/](data/protocol-checks/).
- Pilot (20 Oct, 1,200 episodes): the pre-registered decision was GO ([results/tables/pilot_go_no_go.csv](results/tables/pilot_go_no_go.csv)).
- Main study and secondary run on gpt-oss-120b (21 Oct): complete; results examined in an interim look, recorded in the changelog.
- Main study on mistral-medium-3-5 and claude-sonnet-5-5, nemotron-3-super's exploratory run, and amendment 2's checks: not yet run. They wait for the coauthors' approval of the spending, and run on the analysis frozen at commit `1b7f776` (fingerprints in [prereg/OSF-REGISTRATION.md](prereg/OSF-REGISTRATION.md); no OSF registration, see the changelog).

Episode logs and scored data are kept out of the repository (they are released with the paper); the code reproduces every number from them.

## Quickstart

```sh
make setup                      # uv sync with dev and provider extras
cp .env.example .env            # add API keys; `fplp run` reads .env
make check                      # lint + tests
make run RUN=smoke              # scripted models, no API calls
make analyze RUN=smoke          # score, rates, go/no-go, figure
```

## Spending guard

Runs that call paid models are guarded in code (`src/fplp/budget.py`):

- `fplp run ... --dry-run` prints the episode plan and a cost estimate per model (from earlier logs, or a deliberately high default). It sends nothing.
- A paid run refuses to start without a hard cap, `--max-cost <USD>`, and an explicit confirmation: typing `yes` in a terminal, or `--yes` when run non-interactively. Use `--yes` only after the person paying has approved the run and its cap.
- During the run, no episode starts if it could push spend past the cap; a failed episode is charged for the turns that completed. Every paid run is appended to `data/spend-ledger.jsonl` (local, gitignored), even if it stops early.
- If, after 20 episodes, a model's episodes cost more than 1.5 times the estimate on average, its run stops; rerunning shows a new estimate based on the run's own episodes, for approval.
- A missing API key stops the run before anything is sent. An account error (bad key, no credit, unknown model or host) stops a model's run at once without using up episodes' attempts, and so do ten failures in a row. Ctrl-C starts nothing new and keeps the results of episodes already running.

A first real-model check, once a model is defined in `configs/models.yaml`:

```sh
uv run fplp run configs/runs/pilot.yaml --model <name> --max-episodes 5 --dry-run   # estimate first
uv run fplp run configs/runs/pilot.yaml --model <name> --max-episodes 5 --max-cost 1   # then confirm
uv run fplp show data/raw/pilot/<name>.jsonl --n 3
uv run fplp cost data/raw/pilot --project configs/runs/main.yaml   # budget from real token counts
```

The pilot runs one model at a time, cheapest first, so a harness problem shows before Claude money is spent (each paid step only after approval; caps are examples):

```sh
uv run fplp run configs/runs/pilot.yaml --model gpt-oss-120b --max-cost 2          # all 600, about $0.26
uv run fplp run configs/runs/pilot.yaml --model claude-sonnet-5-5 --max-episodes 10 --max-cost 2   # check
uv run fplp run configs/runs/pilot.yaml --model claude-sonnet-5-5 --max-cost 20    # the rest (resumes)
uv run fplp go-no-go data/processed/pilot.csv                                       # after make score RUN=pilot
```

The main study runs the same way, one model at a time, with a health check (`fplp health`: failures, empty replies, refusals, missing answer lines, wrong host or model, tool errors, per cell; no outcome rates) before each more expensive step. `make run` keeps a Mac awake with `caffeinate`; keep a laptop plugged in with the lid open. Each paid step only after approval; caps are examples:

```sh
make run RUN=main MODEL=gpt-oss-120b MAX_COST=5 YES=1          # every cell's first live run, about $1.81
make run RUN=secondary MAX_COST=3 YES=1                        # descriptive arms, gpt-oss-120b, about $1.06
make health RUN=main MODEL=gpt-oss-120b                        # clean in every cell before going on
make run RUN=main MODEL=mistral-medium-3-5 MAX_EPISODES=10 MAX_COST=2 YES=1
make run RUN=main MODEL=mistral-medium-3-5 MAX_COST=90 YES=1   # about 15 hours at 18 requests/minute
make run RUN=main MODEL=claude-sonnet-5-5 MAX_COST=100 YES=1
make run RUN=exploratory MAX_COST=10 YES=1                     # Nemotron, reported separately
make run RUN=robustness MAX_COST=2 YES=1                       # amendment 2's exploratory checks, about $0.53
make health RUN=main                                           # then make analyze RUN=main, make paper
```

`fplp --help` lists every command; `make help` lists every target.

## Pipeline

1. **Configure.** Models live in `configs/models.yaml`; each experiment is a run config in `configs/runs/` (factor levels, items per cell, arms). Configs are validated strictly: unknown keys and misspelled levels are errors.
2. **Run.** `fplp run` expands the config into conditions, runs every episode for each model, and appends one JSON line per episode to `data/raw/<run>/<model>.jsonl`. Reruns skip finished episodes; failures are logged and retried, up to three attempts in all.
3. **Score.** `fplp score --config <run config>` writes one row per planned episode to `data/processed/<run>.csv`, drops duplicates and episodes from other settings, and reports missing episodes and mixed code versions ([data/README.md](data/README.md) documents both formats).
4. **Analyze.** `fplp hypotheses`, `go-no-go`, `rates`, `model`, `figure` write to `results/` ([docs/analysis.md](docs/analysis.md)).
5. **Write.** The manuscript is kept outside this repository, in `../Manuscript/` next to it; every number it reports comes from `results/`.

## Layout

```
configs/
  models.yaml           model registry (provider, model ID, sampling settings)
  runs/                 smoke, pilot, main, secondary experiment configs
src/fplp/
  cli.py                the `fplp` command
  config.py             run-config and model-registry validation
  conditions.py         factors and the expansion of a config into conditions
  signals/              signal forms, extents, and their renderers
  env/                  mock API: tool schemas, row generators, pagination server
  tasks/                task builders and gold answers
  agents/               model clients: Anthropic, OpenAI-compatible (vLLM), scripted
  episode.py            one episode: a capped tool loop against the mock API
  run.py                `fplp run`
  metrics.py            episode metrics; `fplp score`
  show.py               `fplp show`: transcripts for qualitative review
  cost.py               `fplp cost`: token use, cost, and projections for a planned run
  budget.py             spending guard: estimates, hard cap, confirmation, ledger
  provenance.py         code and environment versions stored with every episode
  analysis/             hypotheses, go/no-go, rates, regression, figure, disclosure, simulation, power
tests/                  unit and end-to-end tests (scripted models, simulated data)
data/                   episode logs and scored tables (generated, gitignored); protocol-check logs
results/                tables and figures cited by the paper
docs/                   signal taxonomy, analysis notes, power analysis, related-work tracker
prereg/                 pre-registration (committed before the pilot)
```

## Reproducibility

- Rows, task items and cursors are derived from fixed seeds; the same config and seed produce the same episodes.
- Every episode record stores the git commit (and whether the working tree had uncommitted changes), the SDK and Python versions, the model's registry entry, the full condition, every tool output the model saw, and the full turn log, including the model and host that served each turn.
- Episode ids hash the model's behavior-relevant settings, so changing a setting starts a fresh set of episodes instead of mixing settings on resume.
- `uv.lock` pins dependencies (CI fails if it is out of date) and `.python-version` pins the interpreter. A model sampled at its default temperature (where temperature 0 is not accepted) runs once per item, for cost; the paper reports this as a limitation, and `replicates` in a run config adds repeats if the budget allows.

## Anonymity, citation and license

The submission is double-blind: keep names and affiliations out of the repository until camera-ready (`CITATION.cff` lists anonymous authors until then), and share code with reviewers through an anonymized mirror.

Released under the MIT License ([LICENSE](LICENSE)).
