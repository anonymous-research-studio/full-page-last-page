# Disclosure-flag validation: the registered sample and a proposed supplement

Prepared 25 Oct 2026, about 14:10 EDT. Nothing has been sent. The worksheets in this folder hold the registered sample plus the proposed supplement.

**Decided 25 Oct, 14:51 EDT:** the full supplement is adopted as proposed, and the registered check alone decides the 0.80 rule. The changelog entry is commit `2267b03` on GitHub `main` (CI run passed); the converter and estimator are commit `f68aa20`. Two coauthors label, Labeler A and Labeler B, without names in the repository. How labels come back and are checked: `RETURNING-LABELS.md`.

## 1. What is registered

**Registration, section 7 (19 Oct):**

> **Disclosure validation.** A random sample of replies to needs-all tasks from the planned main-study episodes, spread evenly across models (`fplp disclosure sample`): 100 incomplete and 100 complete answers in the final-line format, plus 30 per model of H5b's matched pairs with both answers incomplete (up to 380 replies). The two authors label it independently, each on their own copy, seeing the question and the reply without its `COMPLETENESS` line, shuffled and blind to the flag, the stratum and the condition. We report Cohen's κ between the authors; disagreements are resolved by discussion. Against the consensus we report the flag's precision, recall and κ (`fplp disclosure check`). If precision or recall is below 0.80, H5 is tested on the hand labels instead of the flag (section 2), and the rule-based rates are shown only alongside. If neither the flag nor the labels find any disclosure, the two agree on every reply and the flag is used. No LLM judge is used.

**Amendment 1, section 2 (20 Oct), the labeling sample:**

> 100 incomplete final-line answers, 70 of them from the warranted stratum (where disclosures are likeliest, so recall can be estimated) and 30 from the others; the registered plan drew 100 at random; 60 complete answers instead of 100; per model, 20 matched pairs from the warranted completeness-field cells (amended H5b) and 10 from the false-signal cells with both answers incomplete (registered H5b), instead of 30 from the false-signal cells.

**Amendment 1, section 18, the labelers (overlap design):**

> Instead of both authors labeling every reply, the first author labels the whole sample and the second labels a random 100 of it, reshuffled. Agreement (Cohen's kappa) is computed on the overlap; disagreements there are adjudicated; elsewhere the first author's label is used.

**Changelog, 23 Oct:** the 20 warranted pairs per model are drawn "from pairs with an incomplete answer in either format".

**The frozen rule** (`validate_flag`, `hypotheses.py`): the flag is used only if precision and recall are both at least 0.80. If no reply is flagged and no reply is labeled a disclosure, the flag is used. If only one of those classes is empty, the other metric is 0 and the flag fails.

## 2. What the registered sample gives on these data

`fplp disclosure sample` (frozen code) draws **274 replies**: 112 from gpt-oss, 111 from Mistral and 51 from Claude. That's 201 incomplete and 73 complete, with 90 from the false-signal cells. It is fewer than "up to 340" because Claude has no warranted pair with an incomplete answer (amended H5b(a) is not estimable for Claude), so Claude contributes only its 10 false-signal pairs.

**The registered sample contains no flagged reply.** Across the main study, outside the retests, the flag marks:
- 9 of the 3,040 incomplete needs-all answers (Claude 3, Mistral 6, gpt-oss 0);
- 20 of the 9,560 complete ones (Claude 17, Mistral 3).

With 29 flagged replies among about 12,600, a draw of 274 holds fewer than one on average (about 0.6), and this one holds none. On the registered sample, then:
- precision is undefined (nothing flagged);
- if the labelers mark even one reply as a disclosure, recall is 0 and the flag fails, so H5 runs on the hand labels;
- if they mark none, both classes are empty and the flag is used.

So the registered validation measures neither metric. It reduces to one question: do the labelers find any disclosure among 274 unflagged replies?

## 3. Proposal: keep the registered sample, add a weighted supplement

The registered sample stays exactly as drawn. Its labels go through `fplp disclosure check` and, if the flag fails, into the registered hand-label fallback, as registered. **Supplement labels are never passed to `fplp disclosure check` or `fplp hypotheses`:** the frozen code would count them unweighted, and the fallback would test H5 on an enriched sample.

The supplement (from the main study's needs-all replies outside the registered sample, retests left out as the registered sampler does):

| Part | What | Population | Labeled | Weight | Purpose |
|---|---|---|---|---|---|
| F | every reply the flag marks | 29 | 29 (census) | 1 | precision |
| W | unflagged incomplete final-line replies caught by the registered wide-net screen (`fplp disclosure screen`, Amendment 2) | 246 | 246 (census) | 1 | the likeliest missed disclosures |
| U | other unflagged incomplete final-line replies | 1,615 | 120 (seeded random) | 13.46 | missed disclosures elsewhere |
| C | unflagged incomplete completeness-format replies (their prose, without the line) | 969 | 60 (seeded random) | 16.15 | H5b's prose part |

**Estimates:**
- **Precision** is the share of F labeled 1. F is a census, so this is exact up to labeler error; it is reported for all 29 and for the 9 incomplete answers. Interval: Wilson.
- **Recall,** over the incomplete answers H5 uses: TP / (TP + FN̂).
  - TP is the incomplete replies in F labeled 1, at most 9.
  - FN̂ is the disclosures found in the fully labeled sets (W, and the registered sample's 201 unflagged incomplete replies), plus 13.46 × those found in U, plus 16.15 × those found in C.
  - Interval: a bootstrap within parts.

**What this can and cannot show.** TP is at most 9, so recall is decided by how many disclosures the flag misses:
- One missed disclosure in the fully labeled sets puts recall at 9/10 = 0.90 at best; three put it at 0.75.
- One found in U adds about 13.5 to FN̂, which puts recall at about 0.40 even if all 9 flagged replies are true.

In practice the supplement answers what the 0.80 rule asks: does the flag miss disclosures that people see? It cannot certify a recall of 0.80 with a tight interval. With 9 flagged replies in 3,040, no sample can.

**Labeler B's overlap:** the registered random 100, plus 50 from the supplement (10 from F, 25 from W, 15 from U), reshuffled with new ids. Without the supplement part, κ would rest almost entirely on replies both labelers mark 0.

**A leaner option,** if time is short: drop C and label 60 from U. Labeler A then has 609 replies.

## 4. What it changes, and what has to be decided first

- **The supplement is a change to the registered procedure.** It adds a sample that Amendment 1, section 2 doesn't have. Like the 23 Oct entries, it needs a dated changelog entry before any label is made. The entry should say:
  - that the registered sample and `fplp disclosure check` are computed and reported as registered;
  - which estimate decides the 0.80 rule.
- **Which estimate decides is the lead author's call.**
  - If the registered check decides, the supplement is reported beside it as the measurement of precision and recall.
  - In either case, if the labelers find disclosures the flag missed, the registered fallback sends H5 to the hand labels.
- **The labeling load:**
  - Labeler A: 729 replies, about 26,900 words, roughly 3 to 3.5 hours.
  - Labeler B: 150 replies, about 40 minutes.

## 5. Files (this folder)

| Path | For | Content |
|---|---|---|
| `for-labeler-A/` | Labeler A | `worksheet.html` / `.csv`: 729 replies (worksheet id, question, reply without the COMPLETENESS line), shuffled; `labels.csv` (blank: `wid`, `label`, `note`; never overwritten by the builder); `INSTRUCTIONS.md` |
| `for-labeler-B/` | Labeler B | the same for 150 replies, reshuffled, new ids |
| `key.csv` | not for labelers | worksheet ids → episode, part, population, weight, model, condition, flag, evidence seen, stratum |
| `inputs/` | not for labelers | the frozen `fplp disclosure sample` (274 + overlap of 100) and `fplp disclosure screen` outputs |
| `manifest.json` | – | seed (20261025), sizes, counts |

Each labeler's folder holds only what that labeler may see, so it can be sent on its own. The worksheets show no model name, flag, stratum or condition field (checked). Replies sometimes name the API's signal, so blinding to the condition is partial, as PENDING notes. Built by `scripts/disclosure_worksheet.py` from the frozen `fplp disclosure sample` and `fplp disclosure screen` outputs, on the frozen scoring of the main study.

**Written and tested since (commit `f68aa20`):** `scripts/disclosure_labels.py convert` (worksheet ids to the registered `fplp disclosure check` format) and `estimate` (the weighted estimates for the supplement).
