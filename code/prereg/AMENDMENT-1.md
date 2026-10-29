# Amendment 1 to the pre-registration

**Date:** 20 Oct 2026, before any pilot or main-study episode was run.
**Registered plan:** `PREREGISTRATION.md` as committed on 19 Oct 2026 (commit 8077392; verbatim copy in `PREREGISTRATION-registered-2026-10-19.md`). Its registered text is unchanged; changes after registration are listed in its changelog, which points here.

## Why

A design review on 20 Oct 2026 asked whether each registered test can show what its hypothesis claims. It found that several cannot, in both directions: some cannot come out supported whatever agents do, and some come out supported largely by construction. The evidence was the design itself (what the agent sees in each condition) and the protocol checks of 19 Oct (small samples, about 8 items per cell, not results). No pilot or main-study data existed. Because the protocol checks informed these changes, the amendment keeps every registered test, adds corrected tests beside them, and says in advance which tests the paper's claims rest on.

## Rule for reporting

1. **Both families are computed and reported:** the registered tests unchanged (`registered` rows of `fplp hypotheses`), and the amended tests (`amended` rows).
2. **Claims rest on the amended tests** wherever the two differ. Every claim is shown next to the registered verdict, with the reason the amended test replaces it.
3. A registered verdict is never reported as evidence about a hypothesis when the amendment identifies it as decided by construction. It is reported, and labeled as such.
4. **Amended verdicts across models:** supported when supported in a majority of the confirmatory models where the test is estimable, with at least two estimable models. Otherwise the verdict is "not estimable". The registered rule (2 of 3, counting a non-estimable model as not supporting) is reported too.
5. **Hypotheses with several parts:** "not supported" when any estimable part fails; "supported" only when every part is estimable and passes; otherwise "not estimable". A part is not estimable when its cells are empty, when a ceiling or floor leaves no room for the predicted direction, or when it has fewer items than its minimum below.
6. **The registered tests are computed on the cells they were registered for.** The cells added below (the short last page, the completeness field in warranted cells, the documentation arm) are excluded from them, and a test checks that registered results are identical with and without the new cells. The registered sensitivity analysis (empty replies kept as stops) covers both families.

## Changes, each with its reason

### 1. H1 and H2: ceiling and floor (review issue 1)

- **Problem.** With no signal, page 1 looks the same whether or not more rows exist. A model therefore has a single no-signal fetch rate, and H1a needs signals to beat it while H2a needs it to beat terminal signals. A model at a ceiling cannot pass H1a, and one at a floor cannot pass H2a. In the checks, Claude fetched 8 of 8 times with no signal.
- **Problem.** H2b had no variation: gpt-oss-120b and mistral-medium-3-5 fetched 0 of 32 times on page-1-sufficient tasks in every form, and Claude fetched on every lookup and no name-one task in every form. That left zero discordant pairs, so H2 failed whatever agents did at last pages.
- **Change: A1, a new primary test (RQ1-RQ2).** For each main explicit form: fetching when more rows exist minus fetching on a real last page, paired by item, Holm across the five forms. Supported for a model when every form is positive and significant. With no signal the difference is zero by construction; it is reported as a reference.
- **Change: estimability.** H1a is not estimable for a model whose no-signal rate when more rows exist is above 90%. H2a is not estimable when the no-signal rate on a real last page is below 10%. This is the band the pilot rule already used. Amended H1b (issue 6) is likewise not estimable when `total_count`'s rate when more rows exist is above 90%, which leaves no room for the note to be higher.
- **Change.** H2b is its own hypothesis, on the information-matched pair only (`nl_note_json` minus `total_count` on page-1-sufficient tasks); the registered H2b also used the `cursor_plus_note` pair. A floor is a valid null here: the prediction is that the note raises fetching above `total_count`'s rate. Amended H2 is H2a alone.

### 2. H5a: disclosure measured where it is warranted (review issue 2)

- **Problem.** Of 76 incomplete answers in the checks, 22 followed an API that explicitly said the result was complete (a false end signal), and 21 followed a short page with no signal, which looks final. In those cases, not disclosing is the calibrated report from the agent's point of view.
- **Change.** A new column, `disclosure_stratum`, classifies each incomplete needs-all answer:
  - `warranted`: a truthful signal said more rows exist, or a full page came back with no signal under a stated limit and documented pagination (so the documentation arm's no-signal pages are not warranted; its pages with a truthful "more" signal are);
  - `api_said_done`;
  - `short_page`;
  - `no_cue`.
- **Change.** Amended H5a tests the 95% upper bound below 20% on the `warranted` stratum only. The other strata are reported.
- **Change.** Amended H5a needs at least 16 warranted items: with fewer, even zero disclosures leave the Wilson bound above 20% (0 of 15 gives 0.204), and the test would fail by construction.
- **Change: the labeling sample** (`fplp disclosure sample`), which changes the registered procedure:
  - 100 incomplete final-line answers, 70 of them from the warranted stratum (where disclosures are likeliest, so recall can be estimated) and 30 from the others; the registered plan drew 100 at random;
  - 60 complete answers instead of 100;
  - per model, 20 matched pairs from the warranted completeness-field cells (amended H5b) and 10 from the false-signal cells with both answers incomplete (registered H5b), instead of 30 from the false-signal cells.
- **Change.** If the flag fails validation, the registered H5a runs on the hand labels weighted back to each stratum's share of the registered population, because the sample is no longer a simple random sample. Each item still counts once (its labeled episodes averaged), scaled by its episodes' mean weight; the interval uses the Kish effective number of items.

### 3. H5b: the completeness field where disclosure is warranted (review issue 3)

- **Problem.** In the registered main design the field was crossed only with false end signals, where the API asserts completeness and answering "complete" is rational.
- **Problem.** The test kept only pairs where both answers were incomplete, which drops the items where the field made the agent fetch, so it was biased toward a null.
- **Problem.** A reflexive "unknown" would have counted as disclosure.
- **Change.** The main design crosses the field with two warranted cells, on a full page with more rows behind it: no signal, and a truthful `has_more`. That adds 200 episodes per model.
- **Change.** Amended H5b has two parts, and both must hold:
  - (a) *intention to treat* over all matched pairs: the rate of incomplete answers that do not say so is lower with the field;
  - (b) *informativeness* in the no-signal cell, where incompleteness is likeliest: with the field, disclosure is more frequent on incomplete than on complete answers, with a bootstrap over items and a 95% CI above 0. Computing it within one cell keeps a rule like "partial whenever no signal is shown" from passing. The truthful-`has_more` cell's gap is reported descriptively.
- **Change.** Each part needs at least 10 items whose outcome can vary: for (a), items with an incomplete answer in either format; for (b), 10 items with incomplete and 10 with complete answers in the no-signal cell.
- **Change.** The false-alarm rate (`partial` or `unknown` on complete answers) is reported. The registered H5b is computed on the false-signal cells, where it was registered.

### 4. H4 restates H2a (review issue 4)

- **Problem.** A false end signal renders page 1 exactly as a real last page does, and the no-signal page looks the same on both extents. In expectation, H4's contrast equals H2a's. No agent can tell a false end from a true one on page 1.
- **Change.** H4 is presented as the consequence of deferring to terminal signals. Amended H4 tests that consequence: incomplete answers under the false end signals minus under no signal, on the same full pages with more rows behind them. Justified correctness and per-task fetch contrasts are reported alongside.
- **Change.** The wording is "defer to", not "believe". "Worse than no signal" is qualified by task and by the documented interface.

### 5. The no-signal baseline is documented pagination (review issue 5)

- **Problem.** Every tool description says results are paginated and states the limit, so "no signal" means "documented pagination, no signal in the response".
- **Change.** It is labeled that way throughout.
- **Change.** The documentation arm (the description without the pagination sentence) now runs in the main study on every confirmatory model: no-signal pages, needs-all tasks, on full pages with more rows behind them and on real last pages. That adds 200 episodes per model.
- **Change.** The description no longer promises a cursor in forms whose responses carry none ("from a previous response, when it includes one").

### 6. Natural language vs structured fields: information confound (review issue 6)

- **Problem.** `cursor_plus_note` minus `next_cursor` adds the total and the shown range, not just natural language.
- **Change.** Amended H1b uses the information-matched pair only: `nl_note_json` minus `total_count`, which both state the total. The other pair is reported descriptively as "adding a range-and-total note".
- **Change.** A claim that form makes no difference needs equivalence: the 90% CI within ±10 points.

### 7. Task wording cues fetching (review issue 7)

- **Problem.** In the checks, mistral-medium-3-5 fetched on oldest-date tasks 8 of 8 times with no signal and 0 of 24 times on other tasks; the tool says orders come "newest first". 8 of 9 missed fetches under a truthful "more" signal were export tasks. Claude fetched on every lookup to check uniqueness.
- **Change.** The lookup question now states that the order is unique: "C has exactly one order for a ⟨item⟩". (In the checks, mistral-medium-3-5's 0 of 24 is for the core cells; it fetched once in 6 under explicit "all" wording.)
- **Change.** Per-task fetch contrasts are reported for H4.
- **Change.** Sensitivity analyses rerun the amended family without the oldest-date task and without the export task. The export wording is kept: it is neutral by design, and the phrasing arm tests explicit wording.

### 8. Checking is not waste, and H3 needs controls (review issue 8)

- **Change.** `unnecessary_fetch` is renamed `extra_fetch`, and extra calls per episode are reported (`followup_calls`, in `fplp rates`). The figure's x axis is a cost, not an error rate.
- **Change.** A short last page (`last_short`) runs in the main study for every confirmatory model, adding 600 episodes per model. It is the control that separates checking a full page from following the row count: amended H3a needs the fetch rate past a full last page above 50% **and** above the rate past a short last page (both with a truthful signal, paired, significant), so a habit of checking every terminal signal does not pass.
- **Change.** Amended H3 is estimable for a model only when it uses the row count without a signal: fetching after a full page minus after a short page, with no signal, positive and significant.
- **Change.** The reverse direction, the signal over the row count, is added as **H3r**, labeled as formed after the protocol checks. It has the same gate: for an agent that never uses the row count, "signal over row count" is vacuous.
- **Change.** Episodes whose first call asked for fewer rows than the page limit (`own_small_page`) are left out of the amended fetch tests on every extent: on a one-page extent such a page is not the last one, and elsewhere the page boundaries differ from the design. The registered tests keep them, as registered.

### 9. Manuscript claims (review issue 9)

- "Silently wrong" is replaced: the replies state their basis.
- "To avoid floor and ceiling effects" is removed.
- The plan to read a failed H1 as "signals are insufficient" is replaced by the estimability rule.
- The recommendations are tied to the amended tests. The untested harness-verification recommendation is marked as untested.
- "A well-formed response as complete" is removed, since well-formedness is never manipulated.
- The unregistered "Pooled" column is dropped.

### 10. Power analysis (review issue 10)

- **Problem.** The simulation gave no signal a different fetch rate on a real last page than when more rows exist, although the pages look the same. It also modeled no ceilings.
- **Change.** The no-signal rate is now equal on both extents, and per-model rates are supported. `docs/power.md` reports the probability of each amended verdict at check-based rates, an assumption.

### 11. Page-1 content differed by extent (review issue 11)

- **Problem.** On a one-page set, the "later" matches of the count tasks fell onto page 1: 3 to 8 matches, against 1 to 3 on page 1 of a longer set.
- **Change.** A one-page set now gets no later matches. Page 1 shows 1 to 3 matches in every extent (verified: mean about 2.0 in all four).

### 12. Reproducibility and documentation (review issue 12)

- **Change.** The protocol-check error logs are archived with paths and IDs replaced (`data/protocol-checks/errors/`).
- **Change.** `fplp score` warns when a model's turns come from more than one served model version. The served model of the first pilot episodes is recorded in `configs/models.yaml` as `snapshot`.
- **Correction.** The changelog entry of 20 Oct said replaying the archived calls "gives identical results". Rows, offsets, errors and paging flags match; the `cursor_plus_note` message text differs in every such call that returned a page, 299 of the 1,521 (264 in `check-wide`, 21 in `check`, 14 in the rerun), because of the change below.
- **Correction.** Section 9 of the registered plan omits one pre-registration change: the `cursor_plus_note` note was shortened to the `nl_note_json` note alone, dropping "Pass next_cursor to fetch the next page." and "No more results.", so that its contrast with `next_cursor` would isolate the note. That change itself added information (issue 6).
- Temperature 0 is not deterministic on these hosts (rerun final texts matched in 6 and 11 of 15). Host pinning fixes a host, not its weights over time. claude-sonnet-5-5 is one draw per item. All three are stated as limitations.

### 13-14. Minor (review issues 13 and 14)

- **Blind parallel fetches.** `responsive_follow_up` counts only calls issued after page 1 came back. A sensitivity analysis reruns the amended family on it (none were seen in the checks).
- **Smaller pages.** Episodes whose first call asked for a page smaller than the limit are excluded from the amended fetch tests (issue 8).
- **Kept as is, with reasons:**
  - When the limit changes between calls on a short first page, rows overlap. That is how page-number pagination behaves, and coverage is computed from the rows actually returned.
  - Oldest-date justification requires the last row, the only row that establishes the minimum when orders are listed newest first.
  - H5a's interval stays an item-level Wilson interval, which, unlike a bootstrap, gives an upper bound when no answer discloses.

### 15. Deference or scrutiny: a page that shows its own error (H6)

- **Problem.** A false end signal is undetectable on page 1, so H4 shows deference but cannot separate an agent that would scrutinize a response from one that would not.
- **Change.** Two visible-conflict levels show a false end beside a second field on the same page that contradicts it: `visible_conflict_total` (`has_more: false` beside `total_count` equal to the true total, with 20 rows shown) and `visible_conflict_note` (`next_cursor: null` beside "Showing results 1-20 of ⟨total⟩."). Later pages are truthful. Final-line format, needs-all tasks, on a full page with more rows behind it: 200 episodes per model.
- **H6 (formed in this amendment, before any pilot data; not informed by protocol data).** Agents act on a contradicting field on the same page: with a false end beside a field that contradicts it, they fetch more often than under the same false end alone. A positive result shows that agents read past the first signal; it cannot tell noticing the contradiction from following whichever field says more rows exist, and the paper says so.
- **Test.** Pooled over the two pairs (`visible_conflict_total` against `false_end`, `visible_conflict_note` against `false_end_cursor`), paired by item, sign-flip test: positive and significant. Not estimable when fetching under the false ends alone is above 90% (no room to rise). Each pair, and the gap to the truthful signal on the same page, are reported.

### 16. Undocumented interfaces (extends issue 5)

- **Change.** The documentation arm runs on no signal and two forms (`has_more`, `nl_note_json`), on full pages with more rows behind them and on real last pages: 600 episodes per model (400 more than before).
- **Tests.** **A1u**: the signal-value test without the pagination sentence, for both forms, Holm across two. **H1u** and **H2u**: H1a and H2a without it, with the same 10-90% estimability band. This also gives H1a a chance to be estimable for a model at the no-signal ceiling under the documented interface. Claims about undocumented APIs rest on these rows only.

### 17. Reproducibility measured, not assumed (extends issue 12)

- **Problem.** claude-sonnet-5-5 runs once per item at its default temperature, and temperature 0 is not deterministic on the other hosts.
- **Change.** A seeded random 10% of the main study's conditions run a second time on every model (`retest_fraction: 0.1`, arm `retest`): 480 episodes per model. No hypothesis test uses them. `fplp hypotheses` reports, per model, how often the retest matched the first run (share identical and Cohen's kappa) on fetching, evidence seen, correctness and disclosure.

### 18. Labeling: overlap design (changes section 7's procedure)

- **Change.** Instead of both authors labeling every reply, the first author labels the whole sample and the second labels a random 100 of it, reshuffled. Agreement (Cohen's kappa) is computed on the overlap; disagreements there are adjudicated; elsewhere the first author's label is used. That is 440 labels instead of 680. The reason is author time; it is the standard design for estimating agreement.

### 19. Model snapshots recorded

- **Change.** `snapshot` is set in `configs/models.yaml` for gpt-oss-120b (`openai/gpt-oss-120b`) and nemotron-3-super (`nvidia/nemotron-3-super-120b-a12b`), from the served versions logged in the checks. claude-sonnet-5-5's and mistral-medium-3-5's are recorded from their first live episodes (the Claude cap check and the pilot). `fplp score --config` warns on any mismatch.

## Design and cost after the amendment

- **Main study:** 4,800 episodes per model plus 480 retests (5,280; 15,840 in all), up from 3,200. The added cells are the short last page (600), the completeness field in warranted cells (200), the documentation arm (600), the visible conflicts (200) and the retests (480).
- **Estimated cost (dry run):**
  - main study about $203 (gpt-oss-120b $2.32, mistral-medium-3-5 $65, claude-sonnet-5-5 $135);
  - pilot about $15.60, unchanged;
  - secondary about $1.40;
  - exploratory nemotron-3-super about $5.40.
  - About $225 in all.
- **Pilot:** design and go/no-go rule unchanged. Its stimuli change with the environment: the lookup wording, the tool description's cursor sentence, and the number of matches on a one-page set.
- **Secondary run:** its documentation and answer-format arms moved to the main study, on needs-all tasks. Their page-1-sufficient cells, which tested no hypothesis, are dropped.

## Expected verdicts, stated in advance

At rates read off the protocol checks (an assumption; `docs/power.md`), A1 is supported for every confirmatory model in nearly every simulated run, the amended H1 is expected to be "not estimable" overall (no-signal ceiling for claude-sonnet-5-5; `total_count` near the ceiling for mistral-medium-3-5), and the amended H2 is expected to fail for mistral-medium-3-5. The paper reports these outcomes as such; it does not read a non-estimable H1 as evidence for or against signals. H6, A1u, H1u and H2u have no check-based expectation: the protocol checks did not run those cells.

## What the experiments can and cannot establish

- **Can, per model:** whether the first paging decision follows the value of a truthful signal (A1), with and without documented pagination (A1u); whether agents stop at truthful terminal signals on full pages and fetch on truthful "more" signals after short pages; what deferring to a false end costs in answers; whether agents notice a false end when the same page contradicts it (H6); how often agents disclose where disclosure is warranted; whether a completeness field reduces silent incomplete answers informatively; and how reproducible each model's decisions are (the retest).
- **Cannot:**
  - whether agents doubt a false end that nothing on the page contradicts (undetectable by design; H6 covers the detectable case);
  - whether natural language beats structured fields beyond the information-matched pair;
  - undocumented interfaces beyond no signal, `has_more` and the note;
  - how often real APIs send buggy signals (a different study; the paper's recommendation stays conditional).
