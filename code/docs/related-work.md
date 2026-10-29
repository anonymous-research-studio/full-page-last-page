# Related work tracker

Status: `abstract` = abstract verified; `full` = full text read. Do not cite anything below `full` for a specific claim.

| Work | ID | Status | Notes |
|---|---|---|---|
| Petrova, Mazniak, State, *Agents Don't Paginate: First-Chunk Selection for LLM Tool Responses* | arXiv 2608.26130 | full | Checked 23 Oct 2026 (arXiv HTML, v1 of 23 Jun 2026, the only version; the abstract page gives that date despite the 2608 ID). Fatal-risk check passed: no experiment varies has_more, cursors, truncation notes or any completeness signal; the controlled experiments vary the first-chunk value function and the token budget, single turn, no way to fetch more. Both quotes in the manuscript are verbatim (Section 2; Limitations, item 5). The paper does not report which continuation signal the logged agents saw; its own logs are attributed only to Claude Code. |
| Fu et al., *AbsenceBench* (NeurIPS 2025 D&B) | arXiv 2506.11440 | abstract | Placeholder result unconfirmed. |
| *Partial Evidence Bench* | arXiv 2605.05379 | snippet | |
| cuga-agent issue #750 | GitHub | full | Read 23 Oct 2026 (body and the two visible comments; 7 timeline items were not loaded). Model behavior: the agent ignored a pagination rule in its system prompt in 3 of 3 runs (AppWorld `f323bae_1`, Mistral-Medium-3.5, temperature 0.1, 19 of 27 rows), and in a counter-example it walked 16 pages, so it can loop. The fixes are in the harness (a full-page audit). gpt-oss-120b follow-up: the raw signature in 46 of 66 tasks (6 of them passed), with a failed completeness check in 15. The agent's reply is not shown. |
| RFC 8288 (Web Linking) | | | |
| GraphQL cursor connections spec | | | |
| MCP specification (pagination) | | | Pagination covers list operations; check what it says about tool results. |
