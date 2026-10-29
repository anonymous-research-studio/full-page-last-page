# Data

Everything in `raw/` and `processed/` is generated from `configs/` and fixed seeds, so it is gitignored. Archive the final episode logs with the release (an archival DOI host), not in git. The one exception is `protocol-checks/`: the gzipped logs of the runs that tested the harness before registration (see its README).

| Path | Written by | Contents |
|---|---|---|
| `raw/<run>/<model>.jsonl` | `fplp run` | one JSON object per episode (schema below) |
| `raw/<run>/<model>.errors.jsonl` | `fplp run` | failed attempts: `episode_id`, `attempt`, `fatal`, `at`, `condition`, `error`, `traceback`; retried on later runs up to 3 attempts in all, then reported as missing. Account errors (`fatal`: true) stop the run and do not count as attempts |
| `processed/<run>.csv` | `fplp score` | one row per episode (columns below); use `--config` for confirmatory runs |
| `protocol-checks/<run>/<model>.jsonl.gz` | archived by hand | protocol-check episodes, 19 Oct 2026 (tracked in git) |
| `spend-ledger.jsonl` | `fplp run` | one line per paid run: config, cap, estimate, episodes, tokens, cost |

## Episode record (`raw/*.jsonl`)

| Field | Type | Meaning |
|---|---|---|
| `episode_id` | str | hash of the model name, `config_key` and condition; stable across reruns, new when a behavior-relevant setting changes |
| `harness_version` | str | `fplp.__version__` at run time |
| `run_config`, `model_config` | str, object | run config name and the model's registry entry |
| `config_key` | str | hash of the model's behavior-relevant settings (provider, model ID, base URL, temperature, seed, effort, max tokens, `extra_body`, policy) and the tool-call cap |
| `provenance` | object | `harness_version`, `git_sha`, `git_dirty`, `python`, `openai_sdk`, `anthropic_sdk`, taken when the run started |
| `attempt` | int | 1 for a first attempt; higher after earlier failures |
| `max_tool_calls` | int | the tool-call cap for the episode |
| `finished_at` | str | UTC ISO timestamp |
| `model` | str | model name from `configs/models.yaml` |
| `condition` | object | every factor: `signal_form`, `extent`, `task_type`, `task_need`, `item`, `placement`, `conflict`, `documented`, `limit_stated`, `phrasing`, `answer_format`, `page_limit`, `replicate`, `seed`, `arm` (`retest` marks the second run of a seeded random 10% of conditions, used only to measure reproducibility), `more_exists`, `fetch_needed` |
| `question` | str | the user message |
| `target` | object | `tool` and `args` of the query that returns the controlled rows |
| `n_items`, `first_page_size` | int | rows in the target result set; rows on its first page |
| `gold` | object | `answer_type` (`count`, `amount`, `date`, `yes_no`, `id_set`, `sku_any`), `value`, `accepted` |
| `calls` | list | every tool call: `tool`, `arguments`, `is_target`, `paging`, `offset`, `limit`, `n_rows`, `error`, `turn` (the turn that issued it), and `output` (the exact text the model saw) |
| `turns` | list | every model turn: `text`, `reasoning` (when the provider returns it), `tool_calls` (`id`, `name`, `arguments`), `stop_reason`, `tokens_in` (every input token, cached or not), `tokens_out`, `cache_write` and `cache_read` (the parts of `tokens_in` written to and read from the prompt cache; 0 without caching), and as the API reports them `served_model`, `response_id`, `served_by` (the host behind a router) and `system_fingerprint`; on the forced final answer at the cap, `final_tool_choice` (`none`, or `auto` where the host cannot disable tools) |
| `final_text` | str | text of the last turn |
| `empty_reply` | bool | last turn had no text and no tool call (a protocol failure, not a refusal) |
| `stop_reason`, `hit_cap` | str, bool | why the episode ended (`refusal` covers content filters and explicit refusals on every provider); whether the tool-call cap was reached |
| `truncated` | bool | some turn's output was cut at the model's max tokens |
| `tokens_in`, `tokens_out`, `cache_write`, `cache_read` | int | totals over turns (no cache fields in logs from before prompt caching) |

## Scored row (`processed/*.csv`)

Condition columns are copied from `condition` above. Metrics (blank where they do not apply):

| Column | Meaning |
|---|---|
| `follow_up` | any request beyond page 1 of the target query (attempts count) |
| `speculative_fetch` | a later page requested in the same turn as page 1, before any signal was seen |
| `missed_fetch` | 1 − `follow_up`, where a fetch was needed |
| `extra_fetch` | `follow_up`, where no fetch was needed (called `unnecessary_fetch` in the registered draft; a check of a truthful terminal signal can be sensible, so it is reported as a cost) |
| `followup_calls` | number of follow-up requests on the target query |
| `responsive_follow_up` | `follow_up` counting only calls issued after page 1 came back (excludes blind parallel fetches) |
| `own_small_page` | the model's first call asked for fewer rows than the page limit; left out of fetch tests |
| `disclosure_stratum` | for incomplete needs-all answers: `warranted` (a truthful signal said more, or a full page came back with no signal under a stated limit and documented pagination), `api_said_done` (false end signal), `visible_conflict` (false end beside a field that contradicts it), `short_page` (short page, no signal), `no_cue` (full page, no signal, limit hidden or pagination undocumented) |
| `completion` | every row of the target result set retrieved |
| `evidence_seen` | the rows the answer depends on were retrieved (every row for counts, exports and a "no"; the qualifying row for a "yes"; the last row for the oldest date); 0 marks an incomplete answer in H5 |
| `correct` | final answer matches gold |
| `justified_correct` | correct, and for needs-all tasks `evidence_seen` |
| `disclosure_flag` | rule-based flag (`fplp.metrics.disclosure_flag`): the reply, without its `COMPLETENESS:` line, says the answer may be incomplete; validated against hand labels |
| `disclosed` | `disclosure_flag` on incomplete answers (`evidence_seen` = 0) |
| `hedged` | `disclosure_flag` on answers whose evidence was seen (false disclosure) |
| `settled_on_page1` | an exists "yes" whose qualifying row is on page 1 (only when the whole set fits on one page): no fetch is needed whatever the signal, so fetch tests leave it out |
| `stated_completeness` | value of the `COMPLETENESS:` line, if any |
| `empty_reply` | protocol failure flag; excluded from analysis (refusals too) |
| `truncated` | output cut at max tokens; reported, not excluded |
| `n_calls`, `n_target_calls`, `hit_cap`, `stop_reason`, `tokens_in`, `tokens_out`, `cache_read` | cost and termination |
| `requested_limit` | page size the model asked for on its first successful target call (audit column: below the page limit, the one-page extents are no longer one page for that model) |
