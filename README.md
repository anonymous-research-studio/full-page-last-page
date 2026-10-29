# Full Page ≠ Last Page: review artifact

Artifact for the paper "A Full Page Is Not the Last Page: Which Completeness Signals Do LLM Agents Act On?", submitted to ICAART 2027 and anonymized for its double-blind review. Everything the paper says is released or "in the artifact" is here: the environment and analysis code, prompts and tool descriptions (in the code), model configurations, every episode log, the scored data, the pre-registration with its amendments and dated changelog, the hand labels, the code survey's repositories and commits, the literature search's queries, and rendered examples of every signal form. Git history is not included.

## The environment

The environment is a mock retail-operations Web API and the harness that runs a model against it, all in `code/src/fplp/`:

- **The API** (`env/`): three paginated list tools, `list_orders`, `search_products` and `list_tickets`, and one lookup tool, `get_ticket`, served over native function calling. The page limit is 20, and every list tool accepts a cursor or a page number.
- **The signal forms** (`signals/`): how page 1 says whether more rows exist, such as `has_more`, a cursor, a total, a note or no signal (paper Table 3; `examples/rendered_forms.md` shows each one as the model saw it).
- **The tasks** (`tasks/`): the eight task types with their seeded rows and gold answers (paper Table 4).
- **The harness** (`episode.py`, `agents/`, `run.py`): the system prompts, the model clients and the episode loop, capped at 12 tool calls.

Runs and models are configured in `code/configs/`. Scripted agents run without API keys (`cd code && make setup && make run RUN=smoke`); real models need keys (`code/.env.example`).

## The episode logs

An episode is one model answering one question under one condition. Each log line records the condition (signal form, extent, task, item and arm), the question, every tool call with the exact text the model saw, every model turn (with reasoning where the provider returns it), the final answer, the gold answer, token counts and the code version. The full schema is in `code/data/README.md`. To read episodes as transcripts:

```
cd code && uv sync && gunzip -k ../data/raw/main/gpt-oss-120b.jsonl.gz
uv run fplp show ../data/raw/main/gpt-oss-120b.jsonl --n 3
uv run fplp show ../data/raw/main/gpt-oss-120b.jsonl --form none --need needs_all --incomplete --n 3
```

| Run (`data/raw/<run>/`) | What it is | Models | Episodes |
|---|---|---|---|
| `main` | The confirmatory study (paper Sections 5 and 6) | gpt-oss-120b, Mistral Medium 3.5, Claude Sonnet 5.5 | 5,280 each: 4,800 plus 480 retests |
| `secondary` | Secondary conditions: wording, a hidden limit, placement, the secondary forms, a false "more" (Section 4) | gpt-oss-120b | 3,100 |
| `exploratory` | An exploratory fourth model that decides nothing (Section 6.2) | Nemotron 3 Super | 5,274 of 5,280; the other 6 failed all three attempts on a provider rate limit |
| `robustness` | Amendment 2's checks C1 and C2 (Sections 6.8 and 8) | gpt-oss-120b | 1,600 |
| `pilot` | The pilot that decided whether the main study would run (Section 5) | gpt-oss-120b, Claude Sonnet 5.5 | 600 each |
| `reference` | The main study's design run with three scripted policies (follow the signal, count rows, signal else count) for comparison with the models' fetch rates (Amendment 2; no API calls) | scripted | 5,280 each |
| `capcheck`, `nemotron-check` | Live checks before the pilot and before Nemotron's run (a final answer at the tool-call cap; dropped calls, empty replies, refusals); not study data | as named in the files | 3 per model; 30 |
| `code/data/protocol-checks/` | Protocol checks before registration (Section 5) | gpt-oss-120b, Mistral Medium 3.5, Claude Sonnet 5.5 | 768 |

`*.errors.jsonl.gz` files hold failed attempts. Scored episodes, one row per episode, are in `data/processed/`.

## Layout

| Folder | Contents |
|---|---|
| `code/` | The repository as of the last registration changelog entry (no history): the mock API and harness (`src/fplp/`), prompts and tool descriptions (`src/fplp/`), run and model configurations (`configs/`), the analysis (`src/fplp/analysis/`), tests, the protocol-check logs (`data/protocol-checks/`), and the pre-registration, Amendments 1 and 2 and the changelog (`prereg/`). |
| `data/raw/<run>/<model>.jsonl.gz` | Every episode, one JSON object per line (see "The episode logs" above). |
| `data/processed/` | Scored episodes (`fplp score`), one row per episode; `main_fixed` is the second scoring, which is not registered. |
| `results/frozen-analysis-2026-10-25/` | The registered analysis, run with the code frozen before the remaining runs: hypotheses, sensitivity analyses, multiplicity, retests, secondary, exploratory, robustness and reference-agent tables, with logs. H5 there uses the rule-based flag, which later failed validation. |
| `results/h5-on-hand-labels/` | The registered check of the flag and H5 on the hand labels (the decisive H5 results), with logs. |
| `results/paper-tables/`, `results/paper-figure/` | The LaTeX rows and Figure 1 generated from the results (`fplp tables`, `fplp figure`). |
| `results/correctness-audit/`, `results/disclosure-validation/` | The correctness audit's weighted error rates; the disclosure supplement's descriptive precision and recall. |
| `labels/disclosure/` | The labeling worksheets and instructions as the two labelers received them, the key from worksheet ids to episodes, the registered draw, the returned labels (`labeler_A_labels.csv`, `labeler_B_labels.csv`) and their conversion. |
| `labels/correctness-audit/` | The audit samples, worksheets (unblinded and blinded), keys and verdicts. |
| `review-scripts/` | Scripts used beside the registered pipeline: the second scoring and edge-case counts (as patches on the commit the runs used, `545b72b`), the audit and disclosure tools, the scripts behind the paper's descriptive numbers and appendix tables, and the run wrapper. |
| `survey/` | The deployed MCP servers and intermediaries read for the survey (the paper's Appendix): repository and commit (`repos-manifest.tsv`), the reading notes, and the per-tool tally with its counting rule behind the paper's "21 of 61 intermediary tools", plus how the 42 server tools are counted (`intermediary-tally.md`). |
| `litsearch/` | The literature search of 24 October 2026: exact arXiv and web queries and counts (`SEARCH-LOG.md`) and the raw arXiv API results. |
| `examples/rendered_forms.md` | Page 1 of every signal form as the model saw it, taken from the logs. |

## Where the paper's claims are

| In the paper | In this artifact |
|---|---|
| Released environment, prompts and episode logs (abstract, Data Sharing) | `code/src/fplp/` (system prompts in `episode.py`, tool descriptions in `env/tools.py`); every episode in `data/raw/` |
| Audit: 12 of 42 server tools and 21 of 61 intermediary tools with no signal or a silent cap; generators drop headers (Introduction, Appendix) | `survey/`: commits in `repos-manifest.tsv`, line-linked evidence in the two notes files, counts in `intermediary-tally.md` (generators are entries 10 to 15 of the intermediary notes) |
| Protocol checks, 768 episodes (Section 5) | `code/data/protocol-checks/` |
| Pre-registration, Amendments 1 and 2, dated changelog (Section 5) | `code/prereg/` |
| Main study, 5,280 episodes per model, and Tables 6 to 8 (Section 6) | `data/raw/main/`, `results/frozen-analysis-2026-10-25/`, `results/h5-on-hand-labels/`, `results/paper-tables/` |
| Correctness audit, 120 replies (Section 4) | `labels/correctness-audit/`, `results/correctness-audit/` |
| Disclosure labels, 274 replies (Sections 4 and 6.3) | `labels/disclosure/`, `results/disclosure-validation/` |
| Per-task estimates for false end signals (Section 6.2) | `results/frozen-analysis-2026-10-25/tables/posthoc_h4_incomplete_by_task.csv` |
| Stated completeness, 141 trigger-cell and 894 false-end answers (Section 6.3) and the other descriptive numbers | `results/paper-numbers-logs/paper_numbers.txt` |
| Nemotron 3 Super, C1 and C2 (Sections 6.2, 6.8, 8) | `results/frozen-analysis-2026-10-25/tables/exploratory_hypotheses.csv` and `robustness.csv` |
| Full prompts and scoring rules (Appendix) | `code/src/fplp/episode.py`, `code/src/fplp/metrics.py` |
| Literature-search queries (Related Work) | `litsearch/SEARCH-LOG.md` and the raw arXiv results |
| Page 1 of each signal form (Table 3) | `examples/rendered_forms.md` |

## Code versions

- The runs used commit `545b72b` (gpt-oss-120b's main and secondary runs used `467437b`; the changelog of 23 October records that both render identical stimuli). Each episode records its commit.
- The analysis was frozen at commit `1b7f776` before the remaining runs. `code/` is a later snapshot. Its only change under `src/` is `src/fplp/analysis/figure.py` (label placement in Figure 1; presentation only, changelog of 25 October); it adds `scripts/disclosure_worksheet.py`, `scripts/disclosure_labels.py`, their tests and changelog entries.
- `review-scripts/scripts/review_analyses.used-version.py` is the version of `scripts/review_analyses.py` the review analyses ran with.
- `code/README.md` differs from the snapshot in one planning line, removed for review, and a note that its Status section dates from 23 October.
- The registration (19 October) names the venue first planned for the paper (line 131 of `code/prereg/PREREGISTRATION.md`). The paper is under review at ICAART 2027. The registered text is unchanged, so it still matches its SHA-256 fingerprint in `code/prereg/OSF-REGISTRATION.md`.
- The dated commits behind the registration (the paper's Section 5) are in the authors' repository, which stays private during review; the changelog at the end of `code/prereg/PREREGISTRATION.md` records each change with its date.

## Reproducing

Requirements: Python 3.11 or later (3.12 pinned in `code/.python-version`) and [uv](https://docs.astral.sh/uv/); dependencies are locked in `code/uv.lock`. To check the download first, run `shasum -a 256 -c SHA256SUMS` in this folder.

```
cd code && uv sync
gunzip -k ../data/raw/main/*.jsonl.gz && mkdir -p data/raw/main && mv ../data/raw/main/*.jsonl data/raw/main/
uv run fplp score data/raw/main --config configs/runs/main.yaml --out data/processed/main.csv
uv run fplp hypotheses data/processed/main.csv --config configs/runs/main.yaml \
    --disclosure-labels ../labels/disclosure/converted/disclosure_labels.csv --out results/tables/main_hypotheses.csv
uv run fplp tables results/tables/main_hypotheses.csv data/processed/main.csv --config configs/runs/main.yaml
```

The rescored `main.csv` is identical to `data/processed/main.csv.gz`, and the generated table rows match `results/paper-tables/`. To run the tests, install the provider SDKs as well: `make setup && uv run pytest`.

New episodes need API keys (`code/.env.example`); replaying the logs does not.

## Anonymization

Local file paths, an API account identifier in two error logs, and the correctness rater's name were replaced with placeholders such as `<repo>`, `<home>` and `user_<redacted>`. Paths inside `provenance.json` files were rewritten relative to this folder; their SHA-256 values are unchanged. Internal planning notes are not included. `SHA256SUMS` lists every file.
