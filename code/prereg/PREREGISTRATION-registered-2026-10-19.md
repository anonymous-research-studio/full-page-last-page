# Pre-registration: Full Page ≠ Last Page

Status: **registered on 19 Oct 2026** by the dated git commit that adds this version, made before any pilot or main-study episode was run. Changes after that commit go in the dated changelog at the bottom, never in place.

The analysis described here is implemented, before any confirmatory data existed, in `src/fplp/analysis/hypotheses.py` (`fplp hypotheses`), `src/fplp/analysis/go_no_go.py` (`fplp go-no-go`) and the shared tests in `src/fplp/analysis/common.py`, at the commit that registers this file.

## 1. Research questions

- **RQ1.** Which signals, and which forms of them, increase fetching when more rows exist and the task needs them?
- **RQ2.** Do agents stop when a truthful signal says a full page is the last one, and refrain when the first page already answers the task?
- **RQ3.** When the row count and a truthful signal disagree, which do agents follow?
- **RQ4.** Do agents follow a false signal, and do they tell the user when an answer may be incomplete?

## 2. Hypotheses and how each is tested

**Conventions.** All tests run per model. The unit of analysis is the item (task type and item index): every item is seen under every condition, so contrasts are paired by item. Every model runs each item once; if replicates are ever added, they are averaged per item first, so they do not count as independent observations. The test follows the design: paired contrasts use McNemar's exact test with the Agresti-Min adjusted Wald interval when each item contributes exactly one binary outcome per side (one run per item, one form per side), and otherwise (replicates, or forms pooled) a sign-flip permutation test (10,000 permutations) with a percentile bootstrap interval over items. Tests are two-sided at α = .05, with Holm's correction where one part of a hypothesis has several contrasts. "Main explicit forms" are `has_more`, `next_cursor`, `total_count`, `nl_note_json` and `cursor_plus_note`. Unless stated, tests use the core arm, the default answer format, and needs-all tasks. Fetch tests (H1 to H4) leave out exists items answered "yes" by a row on page 1, which happens only in the one-page extent `last_full`: finding a qualifying row settles the question, so no fetch is needed whatever the signal says.

Written in the manuscript draft of 18 Oct 2026, before any real-model run:

- **H1 (RQ1).** When more rows exist and the task needs them, follow-up is lowest with no signal and highest with natural-language and combined signals; structured fields fall between.
  - *Test.* On extent `more_full`: (a) each main explicit form minus no signal, Holm across the five; every difference significant and positive. (b) Each natural-language form minus the structured form that carries the same information: `nl_note_json` minus `total_count` (both state the total) and `cursor_plus_note` minus `next_cursor` (the note added to the cursor), Holm across the two; both significant and positive. Supported if (a) and (b).
- **H2 (RQ2).** On a full page that is the last one, agents fetch more often with no signal than with any truthful terminal signal; natural-language signals raise fetching on page-1-sufficient tasks more than structured fields do.
  - *Test.* (a) No signal minus each main explicit form, on fetching past a full last page (extent `last_full`), Holm across the five; every difference significant and positive. (b) The two contrasts of H1b, on fetching in page-1-sufficient tasks at extent `more_full`, Holm across the two; both significant and positive. Supported if (a) and (b).
- **H3 (RQ3).** Agents follow the row count more than the signal: they fetch past full last pages and stop at short first pages with more behind them.
  - *Test.* Per-item fetch rates pooled over the main explicit forms: (a) on `last_full`, the 95% bootstrap CI lies above 50%; (b) on `more_short`, the 95% CI lies below 50%. Supported if (a) and (b).

Formed on 19 Oct 2026 **after** the protocol checks in section 9, and tested only on data collected after registration:

- **H4 (RQ4).** Agents act on a false end signal: on a full page with more rows behind it, a terminal signal that is false lowers fetching below the rate with no signal at all, and below the rate when the same field truthfully says more rows exist.
  - *Test.* Pooled over the four false end signals (`false_end`, `false_end_cursor`, `false_total`, `false_note`) and their forms (`has_more`, `next_cursor`, `total_count`, `nl_note_json`), on extent `more_full`: (a) fetching with no signal minus fetching under the false signals, significant and positive (a buggy end signal is worse than none); (b) fetching under the same forms' truthful signals minus fetching under the false signals, significant and positive (the signal's value, not the page, drives the stop). Supported if (a) and (b). Each false signal is also reported separately. *Manipulation check, not a test:* a false end signal renders page 1 exactly as a truthful last page does, so fetching under the false signals and on a real last page (same forms) should not differ; we report their difference with a 90% CI. `false_more` (fetching on a false "more" at a true last page) is exploratory and runs in the secondary conditions.
- **H5 (RQ4).** Agents rarely disclose that an answer may be incomplete when they did not retrieve every row it depends on, and requiring a completeness field raises disclosure.
  - *Test.* An answer is *incomplete* when a row it depends on was not retrieved (`evidence_seen` = 0: every row for counts, exports and a "no"; the qualifying row for a "yes"; the last row for the oldest date), on needs-all tasks. *Prose disclosure* means the reply, without its `COMPLETENESS` line, says the answer may be incomplete: the rule-based flag, or, if the flag fails validation (section 7), the authors' consensus labels, in which case both parts are tested on labeled episodes only. (a) Among incomplete answers in the default format (core and false-signal cells), the prose-disclosure rate's 95% Wilson upper bound is below 20%, counting each item once (its incomplete answers averaged). (b) On matched conditions (same item, condition and replicate, answer format aside) where both answers are incomplete, disclosure is higher with the completeness field than without: significant and positive. In the main study the field is crossed only with the four false end signals, so H5b concerns answers left incomplete after a false end signal. With the field, disclosure is prose disclosure or a `COMPLETENESS` line of `partial` or `unknown`; without it, only prose disclosure is possible, and that difference is the treatment. The rate of incomplete answers in each format is reported alongside, because the field may itself change fetching. Supported if (a) and (b).

**Across models.** A hypothesis is supported overall when it is supported in a majority of the confirmatory models (at least 2 of the 3 listed in `configs/runs/main.yaml`); a confirmatory model without usable data counts as not supporting. Other models are reported and not counted. Per-model results are always reported. H1 to H3 are reported as supported or not, whatever the protocol checks suggested.

**Sensitivity.** Every test is repeated with empty replies kept as stops instead of excluded. It is reported and does not change the verdicts.

**Secondary analysis.** A logistic regression of fetching on signal form, with model and task type as fixed effects, form × page-1-sufficient interactions against the no-signal baseline, and item-clustered standard errors (`fplp model --spec fixed`). It is descriptive and does not decide any hypothesis. Terms affected by separation (a cell at 0% or 100%, which gives log-odds beyond ±10 or an undefined standard error) are reported as not estimable. The variational-Bayes mixed model is not used for inference, because on simulated data it understated uncertainty.

**Secondary conditions.** Descriptive and exploratory conditions run on gpt-oss-120b only (`configs/runs/secondary.yaml`) and decide no hypothesis: the secondary forms, the short last page, `false_more`, placement, and the phrasing, limit, documentation and answer-format arms. Each arm is reported as paired contrasts with its base condition (the core cell of its base form on the same extent and task need, run in the same config: no signal, or `has_more` for placement), without a verdict, in the `arms` rows of `fplp hypotheses --config none`; `false_more` is compared with a truthful `has_more` on a real last page.

## 3. Design

- **Signal forms.** Main: `none`, `has_more`, `next_cursor`, `total_count`, `nl_note_json`, `cursor_plus_note` (the cursor plus a note giving the shown range and the total). Secondary (gpt-oss-120b only, exploratory): `link_header`, `page_info`, `nl_note` (outside the JSON), `placeholder_row`. Renderings: `docs/signal-taxonomy.md`.
- **Extents**, crossed with every main form: `more_full` (page 1 full, more rows exist), `last_full` (exactly one full page) and `more_short` (a short first page with more rows behind it). `last_short` (fewer rows than the limit, where the row count and the signal agree on "done") runs in the secondary conditions. Page-1-sufficient tasks run on `more_full` only. Page limit 20. Signals are truthful in every extent.
- **False signals** (conflict arm, page 1 only, needs-all tasks): `false_end` (`has_more: false`), `false_end_cursor` (`next_cursor: null`), `false_total` (`total_count` equal to the rows shown) and `false_note` ("Showing results 1-20 of 20."), all while more rows exist. Later pages are truthful. Each is crossed with both answer formats. A fifth, `false_more` (`has_more: true` on a true last page), runs in the secondary conditions.
- **Tasks.** Needs all rows: filtered count, oldest order date, exists, export, out-of-stock count, priority count. Page 1 suffices: name one, lookup. Every tool carries at least two task types. Needs-all questions avoid "all" and "total" by default. The exists task alternates "yes" and "no" across its occurrences within every cell.
- **Arms.** Main study: the answer format (final line vs a `COMPLETENESS` line) crossed with every false end signal. Secondary (gpt-oss-120b only), one factor from a base condition: phrasing (neutral vs explicit "all", no-signal form, needs-all tasks); limit visibility (stated vs hidden, no-signal form); tool documentation (the default description, which says results are paginated, vs one without that cue, no-signal form); answer format on the no-signal form; placement (top vs bottom, `has_more`).
- **Interface.** Every list tool accepts both `cursor` and `page`; the page limit is stated unless the limit arm hides it; cursors are opaque, server-registered and bound to their query; the tool-call cap is 12 per episode, with a notice only if exceeded.
- **Seeds.** Pilot 3, main 1, secondary 2. The protocol checks used seed 0, so no pilot, main or secondary episode repeats a checked item (tested in `tests/test_specs.py`).
- **Configs.** `configs/runs/pilot.yaml`, `configs/runs/main.yaml`, `configs/runs/secondary.yaml`, as committed with this file.

## 4. Models

Confirmatory set, all first run on 19 Oct 2026 (configs in `configs/models.yaml`):

| Name | Model ID | Access | Settings | Repeats per item |
|---|---|---|---|---|
| gpt-oss-120b | `openai/gpt-oss-120b` | OpenRouter, pinned to the Crusoe bf16 host, no fallbacks | temperature 0, seed 0, reasoning effort medium | 1 |
| mistral-medium-3-5 | `mistralai/mistral-medium-3-5` | OpenRouter, pinned to Mistral's own host, no fallbacks | temperature 0, seed 0 | 1 |
| claude-sonnet-5-5 | `claude-sonnet-5-5` | Anthropic API, directly | effort high; default temperature (temperature 0 is not accepted) | 1 |

Claude Opus 5.5 is not part of the confirmatory set. claude-sonnet-5-5 is sampled once per item at its default temperature, for cost; its per-episode outcomes are therefore one draw, and the paper reports this as a limitation. Provider-side refusal fallbacks are disabled, so every response comes from the model named; each turn's log records the model and host that served it.

## 5. Sample size and stopping

- **Pilot:** 50 distinct items per cell, two models (gpt-oss-120b, claude-sonnet-5-5), four forms (`none`, `has_more`, `next_cursor`, `nl_note_json`), extents `more_full` and `last_full`: 1,200 episodes.
- **Main study:** **100 items per cell**, fixed in advance and not revised after the pilot: 3,200 episodes per model (9,600 in all). The size follows the McNemar sizing in the external review (about 85 to 120 items for one 15-point paired difference at 80% power). Hypotheses that need several contrasts at once have less power: in simulation (`docs/power.md`, one run per item), H1a, which needs all five forms Holm-significant in one model, is supported in 17%, 46%, 74% and 91% of simulated models for a true effect of 15, 20, 25 and 30 points in every form. The protocol checks suggest effects of that size or larger, but they are not used as evidence.
- **Stopping.** Every planned episode is run. A run stopped by its approved spending cap is resumed under a new approval, not abandoned; any condition left incomplete is reported. An episode that fails for provider reasons is attempted up to three times in all and otherwise reported as missing (`fplp score --config` lists missing episodes per model).
- **Pilot data** decide only go or no-go. They are not pooled into the confirmatory analysis.

## 6. Pilot decision rule (go/no-go)

**GO** when both hold:

1. **Protocol health:** under 5% of each model's episodes end with an empty reply.
2. **An informative contrast:** for at least one model, at least one of these has a Holm-corrected p below .05 (Holm across that model's contrasts) and an observed difference of at least 15 points:
   - RQ1: an explicit form minus no signal, fetching when more rows exist, counted only if the no-signal rate lies between 10% and 90%;
   - RQ2: no signal minus a truthful terminal form, fetching past a full last page.

Otherwise **NO GO**: the study is rescoped as the short paper. The rule was set on 19 Oct 2026, after the protocol checks; it decides feasibility, not any hypothesis. It is implemented as `preregistered_decision` in `fplp go-no-go`. In simulation (`docs/power.md`), with 50 items per cell it says GO in 35%, 59% and 82% of pilots for a true RQ1 effect of 15, 20 and 25 points, in 96% for a 25-point RQ2 effect, and in 2.4% when no form differs from no signal.

## 7. Measures, exclusions and scoring

- **Measures.** As defined in `src/fplp/metrics.py` and `data/README.md`: follow-up (any request beyond page 1 of the target query, or a later call that returns rows page 1 did not), missed and unnecessary fetches, completion, `evidence_seen`, justified correctness (correct, with every row the answer depends on retrieved), disclosure, hedging (disclosure on complete answers), stated completeness, speculative fetch (a later page requested alongside page 1), truncation, cost.
- **Exclusions.** Episodes with an empty reply (the last turn has no text and no tool call: a protocol failure) and refusals (including provider content filters) are excluded from every analysis; both are counted and reported per model. Episodes whose output was truncated at the token limit, or that hit the tool-call cap, are kept and reported, unless the truncation left an empty reply, in which case the empty-reply rule applies. A provider error reported mid-response (OpenRouter's `finish_reason: "error"`) fails the attempt, which is retried under the attempt limit.
- **Scoring and provenance.** Confirmatory data are scored with `fplp score --config configs/runs/main.yaml`, which keeps only the episodes the config plans under the registered model settings, drops duplicates, and reports missing episodes, mixed code versions, and episodes run from a working tree with uncommitted changes. Each episode records the git commit, whether the code, configs or lockfile differed from it, SDK and Python versions, and a hash of the model's behavior-relevant settings, which is part of its id.
- **Disclosure validation.** A random sample of replies to needs-all tasks from the planned main-study episodes, spread evenly across models (`fplp disclosure sample`): 100 incomplete and 100 complete answers in the final-line format, plus 30 per model of H5b's matched pairs with both answers incomplete (up to 380 replies). The two authors label it independently, each on their own copy, seeing the question and the reply without its `COMPLETENESS` line, shuffled and blind to the flag, the stratum and the condition. We report Cohen's κ between the authors; disagreements are resolved by discussion. Against the consensus we report the flag's precision, recall and κ (`fplp disclosure check`). If precision or recall is below 0.80, H5 is tested on the hand labels instead of the flag (section 2), and the rule-based rates are shown only alongside. If neither the flag nor the labels find any disclosure, the two agree on every reply and the flag is used. No LLM judge is used.

## 8. Budget and approvals

Estimates from token counts logged in the protocol checks (`fplp run --dry-run`, 19 Oct 2026): pilot about $15.60; main study about $123 (gpt-oss-120b about $1.40, mistral-medium-3-5 about $40, claude-sonnet-5-5 about $82); secondary conditions about $1.50. About $140 in all. Every paid run is approved by the first author before it starts, with a hard spending cap enforced in code (`src/fplp/budget.py`), and recorded in a local spend ledger. An interrupted run starts no new episodes, keeps the results of those already running, and still writes the ledger.

## 9. Protocol checks and review before registration

To be reported in the paper. These runs tested the harness against real models. Their outcomes are not results and are not analyzed; they did inform H4 and H5. The logs are in `data/protocol-checks/`.

- **2026-10-19, `configs/runs/check.yaml`:** 15 episodes each on gpt-oss-120b, mistral-medium-3-5 and claude-sonnet-5-5. The first two were run twice: follow-up and correctness matched in 15 of 15 episodes for both; exact call sequences matched in 13 and 14 of 15 (the others retrieved the same rows with different arguments).
- **2026-10-19, `configs/runs/check-wide.yaml`:** 248 episodes each on gpt-oss-120b and mistral-medium-3-5 and 197 on claude-sonnet-5-5, covering every task type, extent and arm (11 claude-sonnet-5-5 episodes were not run when account credit ran out).

Changes made because of these checks:

1. gpt-oss-120b host changed from DeepInfra to Crusoe: DeepInfra (and Groq) returned the model's tool call inside its reasoning, ending episodes with an empty reply mid-pagination (5 of 5 and 4 of 5 test episodes); Crusoe, AkashML and Cerebras completed 5 of 5. Empty replies are now flagged and excluded.
2. Requests are paced per model (OpenRouter's new-account limit of 20 requests per minute on Mistral; host rate limits on gpt-oss).
3. Scoring: typographic dashes and spaces are normalized; ID answers listed above the final line are read from the whole reply; dates are parsed; justified correctness checks the rows each answer depends on, so valid shortcuts (jumping to the last page) count.
4. The sum task was replaced by the oldest order date: mistral-medium-3-5 retrieved every row in 33 of 40 sum episodes but gave the right total in 4, so sums measured arithmetic rather than pagination.
5. The disclosure patterns were narrowed to explicit uncertainty after they matched narration ("the first page returned 20 orders") and negations ("weren't truncated") in replies that asserted completeness; speculative parallel fetches are scored separately.
6. The false-signal arm was extended from one form to five, and the completeness-field arm moved to the conditions where incomplete answers occur.

An independent review of the code, on 19 Oct 2026 and before any confirmatory data, led to these further changes:

7. Balance: the exists task's yes/no answer alternates within every cell (it had been all "no" in the pilot and all "yes" in the main study); confirmatory runs use fresh seeds, so no item repeats a protocol check; episodes run in a seeded random order, so a run stopped early leaves gaps spread across conditions.
8. Measurement: follow-up also counts a later call that returns rows page 1 did not; cursors are bound to their query; the short first page stays short at any limit; incompleteness for H5 is defined by the rows an answer depends on; the disclosure flag gained recall patterns ("based on page 1 only", "can't be sure", "additional orders may exist") and dropped "at least N"; answer parsing ignores totals ("7 of 40"), page numbers, IDs and dates, and reads "none" as zero. Rescoring all protocol-check episodes with these rules changed no correctness or disclosure outcome.
9. Tests: pairing by item with replicates averaged; McNemar or sign-flip tests chosen by design, with matching intervals; H1b and H2b as two matched pairwise contrasts instead of pooled groups; H5a uses `evidence_seen` and counts each item once; H5b compares matched conditions where both answers are incomplete; the majority rule counts only the confirmatory models; a sensitivity analysis keeps empty replies as stops; the go/no-go rule is stated as a Holm-corrected p value; exists items settled on page 1 are left out of fetch tests.
10. Provenance: episode ids include a hash of the behavior-relevant model settings; each episode stores the git commit, SDK and Python versions and the served model per turn; failed episodes are attempted at most three times; scoring keeps only planned episodes.

A second independent review, also on 19 Oct 2026 and before any confirmatory data, led to these:

11. H4 was restated. Its draft form was an equivalence test of false end signals against true last pages, first with a check that fetching under the false signals is below 50%, then (after the first review) with a suppression part against the truthful signal. But a false end signal renders page 1 exactly as a true last page does, so equivalence holds by construction for any agent. H4 now tests what a false signal costs: fetching under it against no signal (new) and against the same form's truthful signal. Equivalence is kept as a manipulation check. The restatement was made after the protocol-check data had been seen: on those data (8 items, `false_end` only) the restated test holds for gpt-oss-120b and claude-sonnet-5-5 and fails for mistral-medium-3-5, whose fetching without a signal was close to its fetching under the false signal.
12. Disclosure: curly apostrophes are normalized (a confirmatory model writes them, and they had defeated the negation guards); the flag judges the reply without its `COMPLETENESS` line, as the labelers do; the `COMPLETENESS` line is parsed through markdown emphasis; the flag judges spontaneous "Completeness: ..." prose, removing only the structured field; new patterns catch "didn't check the remaining pages", "stopped after the first page" and similar, and false positives such as "may have more than one item" were removed; if the flag fails validation, both parts of H5 use the hand labels, and the labeling sample includes H5b's matched pairs for that purpose. Rescoring all protocol-check episodes with the final rules changed no correctness or follow-up outcome and one disclosure flag, on a reply that said "I didn't check any later pages", which the new patterns now catch.
13. Spending guard: an interrupted run (Ctrl-C) used to keep running queued episodes and skip the ledger; it now cancels them and writes the ledger.

Before registration, the design was trimmed for cost (19 Oct 2026), from about $460 to about $140, without dropping any hypothesis:

14. claude-sonnet-5-5 runs each item once instead of three times; the main study keeps only the cells the hypotheses use (no `last_short`, no descriptive arms, no `false_more`), and those conditions move to the secondary run on gpt-oss-120b only; the pilot grows from 30 to 50 items per cell, raising its chance of GO for a true 25-point effect from 51% to 82%. Main study: 9,600 episodes instead of 23,500.

H1 to H3 were written before the checks and are unchanged in substance; their tests were specified as above before any confirmatory data. H4 and H5 were formed after the checks and are labeled as such; H4 was restated before registration (change 11).

## 10. Timeline

Registration commit: before the pilot. Pilot: 20 Oct 2026. Go/no-go: on pilot completion. Main study: 21 to 22 Oct. Analysis and writing: 23 to 25 Oct. Paper deadline: 25 Oct 2026 (AoE), research track, WWW 2027.

## Changelog

Changes after registration, dated, with the reason. None yet.
