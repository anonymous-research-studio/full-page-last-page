# Common tasks. `make help` lists them. RUN selects a config in configs/runs (default: smoke).
RUN ?= smoke
RAW := data/raw/$(RUN)
SCORED := data/processed/$(RUN).csv
MANUSCRIPT ?= ../Manuscript/current
# On macOS, keep the machine awake during runs (a sleeping laptop stops them; they resume, but lose time)
AWAKE := $(if $(shell command -v caffeinate 2>/dev/null),caffeinate -i ,)

.PHONY: help setup lint test check dry-run run health score analyze paper paper-pilot clean

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install dependencies, including model-provider SDKs
	uv sync --extra dev --extra providers

lint:  ## Lint with the rules pinned in pyproject.toml
	uv run ruff check .

test:  ## Run the test suite
	uv run pytest

check: lint test  ## Lint and test (what CI runs)

dry-run:  ## Print the episode plan and cost estimate for RUN
	uv run fplp run configs/runs/$(RUN).yaml --dry-run

run:  ## Run RUN (resumes; MODEL, MAX_EPISODES). Paid models need MAX_COST=<usd>; YES=1 only after approval
	$(AWAKE)uv run fplp run configs/runs/$(RUN).yaml $(if $(MODEL),--model $(MODEL),) $(if $(MAX_EPISODES),--max-episodes $(MAX_EPISODES),) $(if $(MAX_COST),--max-cost $(MAX_COST),) $(if $(YES),--yes,)

health:  ## Protocol health of RUN, cell by cell (MODEL to limit); no outcome rates
	uv run fplp health $(RAW) --config configs/runs/$(RUN).yaml $(if $(MODEL),--model $(MODEL),)

score:  ## Score RUN's planned episodes into data/processed/RUN.csv (reports missing ones)
	uv run fplp score $(RAW) --config configs/runs/$(RUN).yaml --out $(SCORED)

analyze: score  ## Rates, hypothesis tests and figure for RUN (go/no-go for the pilot only); LABELS=<consensus labels CSV>
	mkdir -p results/tables results/figures
	uv run fplp rates $(SCORED) --out results/tables/$(RUN)_rates.csv
	$(if $(filter pilot,$(RUN)),uv run fplp go-no-go $(SCORED) --out results/tables/$(RUN)_go_no_go.csv,@echo "go-no-go: pilot only")
	uv run fplp hypotheses $(SCORED) --config $(if $(filter main,$(RUN)),configs/runs/main.yaml,none) $(if $(LABELS),--disclosure-labels $(LABELS),) --out results/tables/$(RUN)_hypotheses.csv
	uv run fplp stamp results/tables/$(RUN)_hypotheses.provenance.json $(SCORED) $(LABELS)
	uv run fplp figure $(SCORED) --out results/figures/$(RUN)_calibration

paper:  ## Paper tables and figure from the main study (after `make analyze RUN=main LABELS=...`), copied into MANUSCRIPT
	@test -f results/tables/main_hypotheses.csv || { echo "results/tables/main_hypotheses.csv missing: run make analyze RUN=main first"; exit 1; }
	@if grep -q "not yet validated" results/tables/main_hypotheses.csv; then echo "WARNING: H5 in results/tables/main_hypotheses.csv uses the disclosure flag before validation; after fplp disclosure check, rerun make analyze RUN=main LABELS=<consensus labels CSV>"; fi
	uv run fplp tables results/tables/main_hypotheses.csv data/processed/main.csv --out-dir results/tex
	mkdir -p "$(MANUSCRIPT)/tables" "$(MANUSCRIPT)/figures"
	cp results/tex/*_rows.tex "$(MANUSCRIPT)/tables/"
	cp results/tex/calibration.pdf "$(MANUSCRIPT)/figures/"

paper-pilot:  ## The pilot's go/no-go table for the paper (after fplp go-no-go --out), copied into MANUSCRIPT
	@test -f results/tables/pilot_go_no_go.csv || { echo "results/tables/pilot_go_no_go.csv missing: run fplp go-no-go with --out first"; exit 1; }
	uv run fplp tables --pilot results/tables/pilot_go_no_go.csv --out-dir results/tex
	mkdir -p "$(MANUSCRIPT)/tables"
	cp results/tex/pilot_rows.tex "$(MANUSCRIPT)/tables/"

clean:  ## Remove caches and build output (keeps data and results)
	rm -rf .pytest_cache .ruff_cache build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
