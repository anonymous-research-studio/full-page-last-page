# Signal taxonomy

What the model sees as the tool result on page 1. Rows are abbreviated as `R1 … R20`; in the real output they are full JSON objects, identical across forms for a given item and extent. Examples assume 87 matching rows and a page limit of 20, signals at the bottom (default). Regenerate exact output with `MockAPI(spec).call(...)` if the renderer changes.

Every list tool accepts both `cursor` and `page`, so every form is actionable. The page limit is stated in the tool description unless the `limit` arm hides it.

## Signal forms

| Form | Tier | Source convention | Page-1 tool result (more rows exist) |
|---|---|---|---|
| `none` | main | bare list | `{"results": [R1 … R20]}` |
| `has_more` | main | Stripe v1 | `{"results": [...], "has_more": true}` |
| `next_cursor` | main | Slack, AIP-158, MCP lists | `{"results": [...], "next_cursor": "Pt4So13XV2_G98FyIhWi"}` |
| `total_count` | main | OData, AIP-158 | `{"results": [...], "total_count": 87}` |
| `nl_note_json` | main | message field | `{"results": [...], "message": "Showing results 1-20 of 87."}` |
| `cursor_plus_note` | main | combined / normalizer | `{"results": [...], "next_cursor": "...", "message": "Showing results 1-20 of 87."}` (the cursor plus the same note as `nl_note_json`, so its contrast with `next_cursor` isolates the note) |
| `link_header` | secondary | RFC 8288, GitHub | `{"results": [...], "headers": {"Link": "<https://api.example.com/v1/orders?customer=Riley+Novak&cursor=...&limit=20>; rel=\"next\""}}` |
| `page_info` | secondary | Relay connections (GraphQL) | `{"results": [...], "pageInfo": {"hasNextPage": true, "endCursor": "..."}}` |
| `nl_note` | secondary | MCP fetch server style | `{"results": [...]}` then a new line: `Showing results 1-20 of 87.` |
| `placeholder_row` | secondary | inline marker | `{"results": [R1 … R20, "[… 67 more not shown]"]}` |

### Where each form comes from

- **Standard API conventions:** `has_more` (Stripe), `next_cursor` (Slack, Google AIP-158, MCP list operations), `total_count` (OData, AIP-158), `link_header` (RFC 8288, GitHub) and `page_info` (GraphQL Relay).
- **Agent tooling, not REST:** natural-language notes. MCP's reference fetch server appends a plain-text notice after the content when it truncates (`<error>Content truncated. Call the fetch tool with a start_index of {next_start} to get more content.</error>`), which `nl_note` follows. `nl_note_json` moves the same words into the JSON body as a controlled variant, so wording can be compared with `total_count`, which carries the same information.
- **Candidate designs, no deployed precedent:** `cursor_plus_note` (what an agent tool or harness could add on top of an API's cursor) and `placeholder_row` (an inline marker, as studied for omission detection).

Enterprise APIs use the same mechanisms under other names: Salesforce's query API returns `done` (the inverse of `has_more`) with `nextRecordsUrl` and `totalSize`; Oracle's cloud REST APIs return `hasMore` with `limit` and `offset`; OData services (Microsoft, SAP) return `@odata.nextLink`, absent on the last page. The study tests none of these names or envelopes (paper, limitations: open-web conventions).

## Extents

Signals are always truthful under every extent; the off-diagonal cells are where the row count and the signal point different ways.

| Extent | Rows | Page 1 | Signal says | Row count suggests |
|---|---|---|---|---|
| `more_full` (core) | 41-100 | 20 rows | more | more |
| `last_full` | exactly 20 | 20 rows | done (`has_more: false`, `next_cursor: null`, `total_count: 20`, "Showing results 1-20 of 20.") | more |
| `last_short` | 10-19 | all rows | done | done |
| `more_short` | 41-100 | 12-18 rows | more | done |

`more_short` mirrors specifications that let a page return fewer rows than the limit before the end (Slack, AIP-158, Microsoft Graph).

## False signals (conflict arm)

Page 1 only; later pages are truthful. The four false ends are crossed with both answer formats; the visible conflicts run in the final-line format.

| Conflict | Base form | Extent | Page-1 tool result |
|---|---|---|---|
| `false_end` | `has_more` | more_full | `{"results": [R1 … R20], "has_more": false}` while 87 rows exist |
| `false_end_cursor` | `next_cursor` | more_full | `{"results": [...], "next_cursor": null}` while 87 rows exist |
| `false_total` | `total_count` | more_full | `{"results": [...], "total_count": 20}` while 87 rows exist |
| `false_note` | `nl_note_json` | more_full | `{"results": [...], "message": "Showing results 1-20 of 20."}` while 87 rows exist |
| `false_more` | `has_more` | last_full | `{"results": [R1 … R20], "has_more": true}` on a true last page; page 2 is empty |
| `visible_conflict_total` | `has_more` | more_full | `{"results": [R1 … R20], "has_more": false, "total_count": 87}`: the total contradicts the end (H6) |
| `visible_conflict_note` | `next_cursor` | more_full | `{"results": [...], "next_cursor": null, "message": "Showing results 1-20 of 87."}`: the note contradicts the end (H6) |

## Rendering decisions to defend in the paper

- **One body shape.** All JSON forms use `{"results": [...]}`; `pageInfo` sits beside `results` rather than under `data.<field>`.
- **Link header.** Most function-calling wrappers never pass HTTP headers to the model, so in practice a Link header is usually invisible, which is effectively the `none` condition. We serialize it into the result to test it at all; say so in the paper.
- **Placeholder row** is a string inside an array of objects, so it also tests robust parsing; log parse or argument errors per condition.
- **No MCP envelope.** Results are not wrapped in MCP `CallToolResult`, so its request-status fields cannot act as a spurious completeness cue.
- **Cursors** are opaque and server-registered; `endCursor` is always present, as in GraphQL.
