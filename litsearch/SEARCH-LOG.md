# Literature search, 24 October 2026

## Q7. Search log (for the paper's documentation of the novelty claim)

### Takeaway
On 24 Oct 2026 I ran 16 structured arXiv abstract queries, which returned about 490 titles screened (2023+; one query capped at the newest 200 of 400). I also ran 15 general web searches (about 140 results screened), forward-citation lookups on two citation graphs and backward snowballing from three papers. I read 47 abstracts in batch via the arXiv API, 6 arXiv abstract pages and parts of 7 full texts. The one directly relevant work the manuscript lacks (APIFlow-Bench) surfaced through title screening, not through the pagination keyword, which shows the limit of abstract-only search.

### Cited Findings
- **arXiv API** ([export.arxiv.org/api/query](https://export.arxiv.org/api/query)). Abstract field (`abs:`), all categories, sorted by submission date, results filtered to 2023-01-01 onward. Each line gives the exact `search_query` string, then total hits / titles screened since 2023:
  1. `abs:pagination AND (abs:agent OR abs:agents OR abs:LLM OR abs:LLMs)`: 4 / 4. Relevant: Petrova 2608.26130; DADL 2605.05247 (tool-description language only).
  2. `abs:paginated AND (abs:LLM OR abs:LLMs OR abs:agent OR abs:agents)`: 4 / 4 (same set; arXiv stems terms).
  3. `abs:truncated AND (abs:"tool output" OR abs:"tool outputs" OR abs:"tool response" OR abs:"tool responses")`: 6 / 6. Includes Sethi 2609.14758, OccuBench 2604.10866, DTOC 2609.26121, PACMS 2606.20047, Memex(RL) 2603.04257, context overflow 2511.22729.
  4. `abs:truncation AND (same phrase set)`: 6 / 6 (same set).
  5. `abs:cursor AND abs:API AND (abs:agent OR abs:agents OR abs:LLM)`: 10 / 10, none relevant.
  6. `abs:incomplete AND (abs:"tool output" OR abs:"tool outputs" OR abs:"tool response" OR abs:"tool responses" OR abs:"tool results")`: 8 / 6, none on pagination.
  7. `abs:"partial results" AND (abs:agent OR abs:agents OR abs:LLM)`: 18 / 17, none relevant.
  8. `abs:completeness AND abs:tool AND (abs:agent OR abs:agents) AND (abs:retrieval OR abs:API OR abs:search)`: 400 / newest 200 screened (12 May to 22 Oct 2026). Surfaced APIFlow-Bench 2608.29128, Silent Failures 2609.26836, Agentic Abstention 2606.28733, Premature Commitment 2606.22936, EmailBench 2609.31906, RideWay 2609.17985 and others.
  9. `abs:silent AND (tool output(s) / tool response(s) / tool results / tool failure(s) phrases)`: 12 / 12. Surfaced Kraishan 2610.10062.
  10. `abs:"premature termination" AND (abs:agent OR abs:agents OR abs:LLM)`: 26 / 25. Surfaced 2606.20724 and 2610.30435.
  11. `(abs:"next page" OR abs:"more results" OR abs:"total count" OR abs:"result limit" OR abs:"page size") AND (abs:agent OR abs:agents OR abs:LLM OR abs:LLMs)`: 34 / 30, none relevant.
  12. `(abs:capped OR abs:"result cap" OR abs:"truncated results" OR abs:"truncated search") AND (abs:agent OR abs:agents) AND abs:tool`: 60 / 59. Surfaced ToolBottleneckBench 2610.21098 and BCAS 2603.08877.
  13. `(abs:"tool overuse" OR abs:"unnecessary tool calls" OR abs:"redundant tool calls" OR abs:"over-fetching" OR abs:"excessive tool")`: 36 / 36. Surfaced SMART 2502.11435 and RideWay.
  14. `(abs:"tool output format" OR abs:"tool response format" OR abs:"response format" OR abs:"output format") AND abs:tool AND (abs:agent OR abs:agents)`: 14 / 14. Surfaced 2607.21674.
  15. `(abs:"agent-ready" OR abs:"agent-friendly" OR abs:"agent-native API" OR abs:"API design") AND (abs:LLM OR abs:agent OR abs:agents)`: 37 / 35. Surfaced 2607.12056, 2609.35789 and 2502.17443.
  16. `abs:MCP AND (abs:"tool design" OR abs:"tool descriptions" OR abs:"tool results" OR abs:"server design")`: 38 / 38. Surfaced 2602.14878 and 2608.08467.
- **Abstracts read in full via arXiv API `id_list`: 47.**
  - 2610.10062, 2606.30531, 2606.28733, 2606.22936, 2608.29128, 2605.05247, 2609.17985, 2609.37125, 2609.18217, 2609.10962
  - 2607.21674, 2607.12056, 2502.17443, 2609.35789, 2510.15955, 2610.02627, 2609.31906, 2607.25765, 2511.22729
  - 2609.14758, 2609.26836, 2608.22676, 2608.04591, 2606.13715, 2605.05379, 2604.10866, 2607.20536, 2607.27083, 2607.01641
  - 2603.08877, 2608.08467, 2609.21341, 2602.14878, 2610.30435, 2606.20724, 2609.30604, 2506.11440
  - 2601.06112, 2606.05806, 2510.05968, 2406.19228, 2510.25726, 2509.24002, 2508.14704, 2306.06624, 2410.16464, 2407.18901
- **Abstract pages read: 6.** 2608.26130, 2608.23623, 2610.31650, 2610.16067, 2610.21098, 2606.06460.
- **Full text read in part (targeted extraction through a fetch tool): 7.**
  - Petrova 2608.26130: method, related work and models.
  - Kraishan 2610.10062: faults, models and related work.
  - ToolBottleneckBench 2610.21098: encoding pressure; first 100k of 144k characters.
  - WorkBench Revisited 2606.13715: cap passages.
  - Singh 2609.26836v2: pagination and cap passages.
  - APIFlow-Bench 2608.29128: capabilities and pagination results.
  - APIFlow-Bench repository `schemas.py`, read directly [CODE].
- **Web searches** (general web search tool, about 9-10 results each, 24 Oct 2026). Exact strings:
  1. `"Agents Don't Paginate" first-chunk selection LLM tool responses`
  2. `LLM agents pagination has_more next_cursor tool response benchmark`
  3. `arXiv 2026 LLM agent truncated tool output pagination continuation stop fetching`
  4. `LLM agent API response "has_more" OR "total_count" OR "next_page" experiment incomplete results stop early`
  5. `tool response format JSON vs natural language effect on LLM agent behavior empirical study arXiv`
  6. `agent-ready API design pagination recommendations LLM agents cursor has_more MCP tools`
  7. `Toolathlon OR MCPMark OR "MCP-Universe" agents pagination failure long tool outputs`
  8. `site:openreview.net pagination LLM agents tool responses incomplete results` (filter not strictly applied; 1 OpenReview hit, irrelevant)
  9. `"truncation marker" OR "truncation notice" OR "truncation message" LLM agent experiment tool output continue`
  10. `site:aclanthology.org pagination API LLM agent` (no relevant ACL Anthology paper)
  11. `"Diagnosing Failure Modes in MCP Tool-Using Agents" stage-aware taxonomy evidence-gap` (ICML 2026 listing [icml.cc/virtual/2026/77938](https://icml.cc/virtual/2026/77938); snippet says 427 MCP-Atlas tasks and a six-stage taxonomy; no pagination mentioned) [SNIP]
  12. `Speakeasy OR Stainless MCP server pagination LLM agents recommendation "has_more" OR cursor tool design blog`
  13. `study LLM agents stop after first page of API results controlled experiment completeness signal 2026`
  14. `ICLR 2027 OpenReview submission tool output truncation agents incomplete tool results`
  15. `OpenAI function calling best practices tool results large outputs pagination guidance`
- **Primary guidance pages read:** Anthropic engineering post; MCP spec 2025-06-18 pagination; Google AIP-158; LatentEval; Digital Applied; kage #143; Arcade ToolBench "improve" page (no pagination content found).
- **Forward citations:**
  - Semantic Scholar Graph API: AbsenceBench (arXiv:2506.11440) returned 12 citing records, including CROWN 2608.04591 and EpiSEM-Bench 2610.31650, which were both read. Requests for Petrova (2608.26130), Sethi (2609.14758) and Kraishan (2610.10062) failed with HTTP 429 rate limits after three retries.
  - OpenAlex API: Petrova, Sethi, AbsenceBench, Kraishan and Styles each show 0 citing works. Because AbsenceBench also shows 0 there, the OpenAlex graph is lagging and the result is uninformative ([OpenAlex](https://api.openalex.org/works/doi:10.48550/arXiv.2608.26130)).
- **Backward snowballing:**
  - Petrova related work cites no pagination study. The nearest is Frees 2025, ResourceLink patterns for large datasets in MCP ([2510.05968](https://arxiv.org/abs/2510.05968)).
  - Kraishan related work led to Sun et al. 2024, ReliabilityBench, ToolMaze and PALADIN ([2509.25238](https://arxiv.org/abs/2509.25238)).
  - kage #143 lists 25 arXiv IDs. I screened them by the claims the issue attributes to them and read two abstracts (2610.16067, an oracle-failure audit; 2610.21098).

### Inferences
- **Suggested one-sentence description for the paper, to adapt:** "On 24 October 2026 we searched arXiv abstracts (all categories, 2023 onward; 16 queries combining pagination, cursor, truncation, result-cap, completeness and tool-response-format terms with agent or LLM terms), Semantic Scholar citations of AbsenceBench, and the general web including OpenReview, ACL Anthology, the MCP specification and vendor guidance (15 queries). We screened about 630 records, read 53 abstracts and 7 full texts, and found no study that varies the completeness signal with rows held fixed (Appendix X)."
- **Search by abstract keyword alone would miss benchmarks that bury pagination in a capability list.** APIFlow-Bench is the proof. The paper should say that title screening and full-text checks of the closest benchmarks supplemented the keyword search.

### Gaps
- **Not searched directly:**
  - Google Scholar (no API access), so the planned Google Scholar step is undone.
  - The ACM Digital Library's 2025 and 2026 proceedings (only via web search, which found nothing).
  - OpenReview's own search, and ICLR 2026, NeurIPS 2025/2026 and COLM 2025/2026 listings (only via site-restricted web search).
  - The ACL Anthology search interface.
- **Forward citations of Petrova, Sethi and Kraishan are still unknown** because of rate limits.
