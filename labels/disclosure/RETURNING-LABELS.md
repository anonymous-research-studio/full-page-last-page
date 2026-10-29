# Disclosure labels: how they come back, how they are checked, and what H5 does

Written 25 Oct 2026, about 14:55 EDT, for the lead author. Not for the labelers: it names the parts of the sample.

## 1. What comes back

Each labeler returns one file, the `labels.csv` from their folder, filled in:
- columns `wid`, `label`, `note`;
- one row per worksheet id (729 for Labeler A, ids `A001`–`A729`; 150 for Labeler B, ids `B001`–`B150`);
- `label` is `1` (the reply says or implies the answer may be incomplete) or `0`, on every row; `note` is free text.

Both files are called `labels.csv`, so rename them on receipt: save them as `returned/labels_A.csv` and `returned/labels_B.csv` in this folder. Don't overwrite the blank templates in `for-labeler-A/` and `for-labeler-B/`; their fingerprints are in the changelog. If a labeler sends a spreadsheet (`.xlsx`, `.numbers`), export it to CSV first.

## 2. How they are checked before use

`scripts/disclosure_labels.py convert` (commit `f68aa20`) checks both files and writes nothing if any check fails. It reports every problem at once:
- **Columns** are matched by name, so reordered or extra columns are fine. The file must have `wid` and `label`.
- **Ids:** every worksheet id appears exactly once. Missing, extra and duplicated ids are listed.
- **Labels:** every row has 0 or 1. Blank labels and any other value are listed, with their ids. A spreadsheet's `1.0` is read as 1.
- **Swapped files:** if Labeler B's file is passed as Labeler A's, it says the files may be swapped.
- **Encoding:** UTF-8, with or without a byte-order mark. A file re-saved as Mac Roman is read with a warning; ids and labels are ASCII, so only notes can be affected.
- **The key:** both worksheets' ids must match `key.csv`, and the key's registered part must equal the frozen sampler's draw in `inputs/` (274 replies, and the 100 of Labeler B's overlap).

It then writes, in `returned/converted/`:

| File | Content | Goes to |
|---|---|---|
| `labels_a.csv` | the 274 registered replies, `episode_id,label` (Labeler A) | `fplp disclosure check` |
| `labels_b.csv` | the registered overlap of 100, `episode_id,label` (Labeler B) | `fplp disclosure check` |
| `to_adjudicate.csv` | every disagreement on the 150 overlap replies: episode id, both worksheet ids, question, reply, both labels and notes. No flag, part or condition | the two labelers, to settle by discussion |
| `supplement_labels.csv` | the 455 supplement replies with part, weight, flag and consensus label | `estimate` only, never `fplp hypotheses` |

## 3. Steps, in order

**Correction, 25 Oct, about 16:25 EDT:** this disk ignores letter case in file names, so convert's outputs `labels_a.csv` and `labels_b.csv` would overwrite the returned `labels_A.csv` and `labels_B.csv` if written to `returned/`. Every command below now writes to `returned/converted/`; the labels were converted that way, and the returned files are unchanged (same SHA-256).

From the `fplp-analysis` folder. `fplp-frozen.sh` runs the frozen analysis (commit `1b7f776`); a copy is in `REVIEW/results-2026-10-25/scripts/`.

```
# 1. check and convert
.venv/bin/python scripts/disclosure_labels.py convert --dir REVIEW/disclosure \
    --labels-a REVIEW/disclosure/returned/labels_A.csv --labels-b REVIEW/disclosure/returned/labels_B.csv \
    --out-dir REVIEW/disclosure/returned/converted
# 2. the labelers settle each row of returned/converted/to_adjudicate.csv; write adjudicated.csv with columns episode_id,label
# 3. convert again with the adjudications (it refuses ids that are not disagreements)
.venv/bin/python scripts/disclosure_labels.py convert ... --adjudicated REVIEW/disclosure/returned/converted/adjudicated.csv
# 4. the registered check, frozen code, registered sample only
fplp-frozen.sh disclosure check $PWD/REVIEW/disclosure/returned/converted/labels_a.csv $PWD/REVIEW/disclosure/returned/converted/labels_b.csv \
    $PWD/data/raw/main --config configs/runs/main.yaml --adjudicated $PWD/REVIEW/disclosure/returned/converted/adjudicated.csv \
    --out $PWD/REVIEW/disclosure/returned/converted/disclosure_labels.csv
# 5. the registered analysis with the consensus labels (make analyze RUN=main LABELS=...), frozen code
fplp-frozen.sh hypotheses $PWD/REVIEW/results-2026-10-25/processed/main.csv --config configs/runs/main.yaml \
    --disclosure-labels $PWD/REVIEW/disclosure/returned/converted/disclosure_labels.csv --out <new results folder>/main_hypotheses.csv
# 6. the supplement's estimates (descriptive)
.venv/bin/python scripts/disclosure_labels.py estimate --dir REVIEW/disclosure --returned REVIEW/disclosure/returned/converted \
    --consensus REVIEW/disclosure/returned/converted/disclosure_labels.csv --out REVIEW/disclosure/returned/converted/supplement_estimates.csv
```

Adjudicate every disagreement before step 4. The frozen check leaves unsettled disagreements out, so if the only 1s were among them, the check would pass the flag. `estimate` refuses to run while any disagreement is open.

## 4. What H5 does in each case, under the registered rule

The frozen rule (`validate_flag`) uses the flag if precision and recall are both at least 0.80. When no reply is flagged and none is labeled 1, flag and labels agree on every reply and the flag is used. When only one of those classes is empty, the flag fails. It runs once, on the registered sample pooled across models.

Tested on dummy labels on the real worksheets: each case went through `convert`, the frozen `fplp disclosure check` and the frozen `fplp hypotheses` (inputs, logs and outputs in `dummy-test-not-results/`; the labels there are invented).

**The labelers find no disclosure in the 274 registered replies.** Precision and recall are both undefined, so the flag is used. H5 is exactly the provisional result in `results_provisional.md`.
- The dummy run reproduced every row of `main_hypotheses.csv`. The only change was in 12 test descriptions: "rule-based flag (not yet validated)" became "(validated)".
- This holds even if they find disclosures in the supplement only (dummy scenario 3: 12 marked 1, all in the supplement). The supplement is reported beside H5 and cannot switch it.

**They find one or more disclosures the flag missed among the 274.** No registered reply is flagged, so precision is undefined, recall is 0 and the flag fails. H5 is then tested on the hand labels of the 274 registered replies alone. The H5b(b) part instead reads the `COMPLETENESS` line on every episode (changelog, 23 Oct).

What each part runs on, from the dummy run. These counts depend only on which replies are labeled, so they hold for any real labels:

| Part | gpt-oss-120b | mistral-medium-3-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Registered H5a: labeled incomplete answers in the registered cells, weighted back to each stratum's share (Kish interval) | 43 items | 40 items | 19 items |
| Registered H5b: labeled false-signal pairs, both answers incomplete | 10 items | 10 items | 10 items |
| Amended H5a: labeled warranted incomplete answers (needs 16 items) | 33 items | 35 items | 1 item: not estimable |
| Amended H5b(a): labeled warranted pairs (needs 10 items); also a rescaled row | 19 items | 20 items | 0: not estimable |
| Amended H5b(b): the `COMPLETENESS` line alone, every episode | as under the flag (needs no label) | as under the flag | not estimable, as under the flag |
| H5b(b) on labeled episodes, reported beside it | not estimable | not estimable | not estimable |

With dummy labels, the overall verdicts came out as they do under the flag: registered H5 not supported, amended H5a supported (2 of 2 estimable models), amended H5b not supported. Two per-model rows moved: Claude's registered H5a (supported, then not) and gpt-oss's amended H5b(a) (supported, then not). Real labels can move other rows.

**The flag's precision is undefined.** On the registered sample it always is, because the sample holds no flagged reply. So precision never decides on its own.
- If recall is also undefined (no label of 1), the flag is used: the first case.
- If recall is 0 (any label of 1), the flag fails: the second case.

The supplement's precision is defined, on all 29 flagged replies, but it is descriptive only.
