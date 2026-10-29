# Protocol-check logs

Episode logs from the runs that tested the harness against real models on 19 Oct 2026, before the pre-registration was committed. They are kept for transparency and are reported in the paper as protocol checks. They are not results: no hypothesis is tested on them, and no confirmatory episode reuses their items (the checks use seed 0; the pilot, main and secondary runs use seeds 3, 1 and 2).

| Folder | Config | Episodes |
|---|---|---|
| `check/` | `configs/runs/check.yaml` | 15 each on gpt-oss-120b, mistral-medium-3-5, claude-sonnet-5-5 |
| `check-rerun/` | the same config, run a second time | 15 each on gpt-oss-120b and mistral-medium-3-5 (temperature 0) |
| `check-wide/` | `configs/runs/check-wide.yaml` | 248 each on gpt-oss-120b and mistral-medium-3-5; 197 on claude-sonnet-5-5 |

Notes:

- The rerun matched the first run on follow-up and correctness in 15 of 15 episodes for both models. Exact call sequences matched in 13 of 15 (gpt-oss-120b) and 14 of 15 (mistral-medium-3-5); the others retrieved the same rows with different arguments. Final texts matched in 6 and 11 of 15.
- `check-wide` includes 40 episodes each of the retired `sum` task on gpt-oss-120b and mistral-medium-3-5. It was replaced by the oldest order date before the claude-sonnet-5-5 run, because mistral-medium-3-5 retrieved every row in 33 of 40 sum episodes but gave the right total in 4. 11 claude-sonnet-5-5 episodes were not run when account credit ran out.
- The logs predate the provenance fields (`provenance`, `config_key`, per-turn `served_model`) and the current episode-id scheme. Their `harness_version` is 0.1.0, and they were written by the code before the pre-registration commit.
- `errors/` holds the protocol checks' error logs (amendment 1): 11 claude-sonnet-5-5 episodes in `check-wide` that failed when account credit ran out, and 7 mistral-medium-3-5 episodes in `check` that hit OpenRouter's new-account rate limit. Local file paths, account IDs and request IDs are replaced by placeholders (`<repo>`, `<home>`, `user_<redacted>`, `req_<redacted>`).
- `check-wide` used the `cursor_plus_note` wording of that time, which ended with "Pass next_cursor to fetch the next page." (or "No more results." on a last page). It was shortened before registration to the `nl_note_json` note alone. Replaying the archived calls through today's mock API gives the same rows, offsets, errors and paging flags, but different message text for every `cursor_plus_note` call that returned a page (299: 264 in `check-wide`, 21 in `check`, 14 in the rerun), so impressions of that form from the checks do not carry over.
- Calls in these logs have no `turn` field (it was added later), so `speculative_fetch` scores 0 for them by default; a separate check found no archived episode that paged in its first turn.
- At temperature 0, the rerun matched the first run's final text in 6 of 15 episodes (gpt-oss-120b) and 11 of 15 (mistral-medium-3-5): temperature 0 is not deterministic on these hosts.

Score them like any other logs; `fplp score` reads the gzipped files directly and drops the retired task:

```sh
uv run fplp score data/protocol-checks/check-wide --out data/processed/check-wide.csv
```
