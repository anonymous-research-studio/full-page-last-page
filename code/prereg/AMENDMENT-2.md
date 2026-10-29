# Amendment 2: exploratory checks and safeguards (21 October 2026)

Status: committed on 21 October 2026, after the interim look at gpt-oss-120b's main-study and secondary results (changelog, 21 Oct) and before any episode of mistral-medium-3-5's or claude-sonnet-5-5's main study, nemotron-3-super's exploratory run, or the checks below. The pre-registration and Amendment 1 are unchanged.

## Why

A devil's-advocate review of the design and of gpt-oss-120b's interim results raised objections a skeptical reviewer would make. Two concern how to read gpt-oss-120b's results, and can be checked cheaply:

1. The no-signal baseline depends on the tool description: without the pagination sentence, gpt-oss-120b's no-signal fetching rose from 34% to 61%. The default description says a cursor comes "from a previous response, when it includes one". That clause may itself act as an end cue.
2. A `total_count` equal to the rows shown did not stop gpt-oss-120b past a real last page (33% fetched, against 0 to 8% for the other truthful end signals). `total_count: 20` may read as "20 results on this page" rather than as a total.

The others are answered by analysis, documentation and framing (sections 3 to 7).

## Rules

1. Everything in this amendment is exploratory or descriptive. It decides no hypothesis and changes no registered or amended test, verdict rule, exclusion, design cell or item of the main study.
2. The checks were formed after seeing gpt-oss-120b's results and are reported as such.
3. The contrasts and their interpretation are fixed below, before any of their episodes run.

## 1. Exploratory checks (gpt-oss-120b only; `configs/runs/robustness.yaml`)

One run of 1,600 episodes on fresh items (seed 11), needs-all tasks, extents `more_full` and `last_full`, 100 items per cell; estimated cost $0.53. It runs only after the coauthors approve the spending.

- **C1, wording.** A new tool-description level, `plain`, drops only ", when it includes one" from the pagination sentence and from the `cursor` parameter's description; everything else is identical (`src/fplp/env/tools.py`; tested in `tests/test_amendment2.py`). It runs on no signal, `has_more` and the JSON note, beside the default wording on the same items.
  - C1a, C1b: no signal, plain minus default, when more rows exist and on a real last page.
  - C1c to C1f: the same for `has_more` and the JSON note (descriptive).
  - Interpretation, fixed in advance: if C1a and C1b are positive (plain raises no-signal fetching), the clause acts as an end cue, and the no-signal baseline in the main study is partly a weak end signal. If they are near zero, the cue lies elsewhere in the paging documentation, and the baseline caveat stands without that explanation.
- **C2, the total's name.** A new signal form, `total_matches`, renders the same number as `total_count` under an unambiguous name (`src/fplp/signals/render.py`). Both run on the same items.
  - C2a: on a real last page, `total_matches` minus `total_count`. Negative means the unambiguous name reads more as "done".
  - C2b: when more rows exist, the same difference.
  - Interpretation, fixed in advance: a clearly negative C2a means the field's name explains part of `total_count`'s weakness as an end marker. A C2a near zero means a total equal to the rows shown is a weak end marker whatever its name.
- Computed by `fplp robustness` (paired by item, 95% intervals, the amended exclusions). Not run on the other models; extending either check would be a separate, dated decision.

The configuration, existing episode ids and the main study are unaffected: the new wording is left out of the condition record at its default, so every recorded episode keeps its id (checked against the main, secondary and pilot logs).

## 2. Reference agents (descriptive; `configs/runs/reference.yaml`)

The main study's exact design, seed and items, run with three scripted agents at no cost: one follows the hint, one counts rows, one follows the hint when there is one and counts rows otherwise. `fplp reference` sets a model's fetch rates beside theirs, cell by cell. Where a model departs from all three simple rules is where its behavior is not "obvious".

## 3. One correction across all main contrasts (sensitivity)

`fplp multiplicity` applies Holm and Benjamini-Hochberg corrections across every main contrast of the amended family per model, in place of Holm within each hypothesis part. It changes no verdict. Tests decided by a bound rather than a p value (H3a, H3b, H5a, and H5b's informativeness part) are not included.

## 4. Disclosure screen

`fplp disclosure screen` lists incomplete answers the rule-based flag did not mark whose reply contains hedging or limiting language, for the hand labelers to read first. It decides nothing. The flag is not changed after seeing data: if it misses disclosures, the registered fallback applies (H5 is tested on the hand labels when the flag's precision or recall is below 0.80).

## 5. Real-world wrong signals

The paper cites public reports that deployed APIs send wrong end signals, as evidence that they occur (not of how often). The clearest: the Atlassian MCP server's Jira search tool returned no next-page token and a `totalCount` equal to the page size, so agents treated the first page as complete (atlassian/atlassian-mcp-server, issue 118, opened 20 March 2026); and the Atlassian Marketplace API dropped its `next` link early because of a miscount (Atlassian MP-286, December 2024).

## 6. Framing

A1 is necessary, not sufficient: it shows that agents act on the value of the signal, not that they reason about completeness. Whether an agent follows the signal in both directions is read from A1 together with H3r, and reported descriptively.

## 7. Third-party timestamps

GitHub records when each commit reached it, through the continuous-integration run it triggered: the registration commit `8077392` at 2026-10-20 01:17 UTC (19 October, US Eastern time) and Amendment 1, `b15cc3c`, at 2026-10-20 14:57 UTC, both before the first pilot episode. Before the remaining runs start, this state of the repository (this amendment included) is registered on OSF, so that for mistral-medium-3-5, claude-sonnet-5-5 and the checks above an outside record shows the analysis was fixed before their data existed (`prereg/OSF-REGISTRATION.md`).
