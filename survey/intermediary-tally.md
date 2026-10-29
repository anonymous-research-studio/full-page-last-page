# Intermediary tools by signal handling: per-tool tally

The counting rule and tally behind the paper's "21 of 61 intermediary tools" (introduction), its "103 MCP server and intermediary tools" (contributions) and the intermediary counts in its Appendix. Added to the artifact on 29 Oct 2026; the tally itself was written on 25 Oct 2026.

The source is `notes-community-servers-generators-gateways-wrappers.md` in this folder, its summary table (29 entries) and per-entry evidence (checked 2026-10-24). An earlier draft said 54 tools. No tally behind that number is recorded, and it cannot be reproduced from the notes under any single counting rule. The 21 tools with no signal or a silent cap reproduce exactly.

## Counting rule

- **One row per tool** named in the notes' "Tool(s) examined" column. A generic set ("generated tools", "search / query tools", "Slack.ListConversations etc.") counts once. A tool gets one row per mode only where the notes code its modes separately (Jira Cloud and Jira Data Center in entry 1).
- **The category is the notes' own code for that tool**, mapped to the paper's categories:
  - EXPLICIT-END → explicit end value;
  - OMIT-END → end by omitting a field;
  - TOTAL-ONLY → total only;
  - NL-NOTE → natural-language note;
  - SILENT-CAP → no signal or silent cap, as is HEADER-LOSS where the notes say the result carries no signal;
  - AUTO-PAG → returns or fetches every page;
  - PRESERVE → passes the upstream body through;
  - not applicable, model-controlled or could not determine → other or undetermined.
- **Tools with two codes:**
  - The final code decides: Pipedream's "AUTO-PAG to cap, then SILENT-CAP" counts as silent cap.
  - A note's default mode decides: Notion's default JSON counts as pass-through.
  - Composio's "PRESERVE + OMIT-END (inferred)" counts as pass-through, because the omission is the upstream API's own convention.
  - Klavis's Jira row, "PRESERVE/TOTAL-ONLY", counts as total only, because a total is what the model can use.

## Tally

| # | Entry | Tool (mode) | Code in the notes | Category in the paper |
|---|---|---|---|---|
| 1 | mcp-atlassian | jira_search (Cloud) | OMIT-END | omission |
| 1 | mcp-atlassian | jira_search (Data Center) | TOTAL-ONLY | total only |
| 1 | mcp-atlassian | confluence_search | SILENT-CAP | no signal / cap |
| 2 | slack-mcp-server | conversations_history | OMIT-END | omission |
| 2 | slack-mcp-server | conversations_replies | OMIT-END | omission |
| 2 | slack-mcp-server | conversations_search_messages | OMIT-END | omission |
| 3 | google_workspace_mcp | search_gmail_messages | NL-NOTE | NL note |
| 3 | google_workspace_mcp | search_drive_files | OMIT-END ("nextPageToken" line only when more) | omission |
| 4 | Gmail-MCP-Server | search_emails | SILENT-CAP | no signal / cap |
| 5 | mcp-notion-server | search / query tools | PRESERVE (default JSON) | pass-through |
| 6 | gitlab-mcp | list_issues | SILENT-CAP + HEADER-LOSS | no signal / cap |
| 6 | gitlab-mcp | list_merge_requests | SILENT-CAP + HEADER-LOSS | no signal / cap |
| 6 | gitlab-mcp | search_repositories | OMIT-END | omission |
| 6 | gitlab-mcp | discussions | EXPLICIT-END | explicit |
| 7 | airtable-mcp-server | list_records | AUTO-PAG | every page |
| 7 | airtable-mcp-server | search_records | AUTO-PAG | every page |
| 7 | airtable-mcp-server | list_comments | PRESERVE | pass-through |
| 8 | brave-search-mcp-server | brave_web_search | SILENT-CAP | no signal / cap |
| 9 | postgres-mcp | execute_sql | not applicable (query-controlled) | other |
| 10 | FastMCP from_openapi | generated tool | PRESERVE + HEADER-LOSS | pass-through |
| 11 | Stainless | legacy per-endpoint tool | PRESERVE + HEADER-LOSS | pass-through |
| 11 | Stainless | Code Mode | model-controlled | other |
| 12 | Speakeasy / Gram | SDK-embedded tool | PRESERVE + HEADER-LOSS | pass-through |
| 12 | Speakeasy / Gram | standalone generator | PRESERVE + HEADER-LOSS | pass-through |
| 12 | Speakeasy / Gram | Gram HTTP tool | PRESERVE + HEADER-LOSS | pass-through |
| 13 | openapi-mcp-generator | generated tools | PRESERVE + HEADER-LOSS | pass-through |
| 14 | fastapi_mcp | generated tools | PRESERVE + HEADER-LOSS | pass-through |
| 15 | mcp-openapi-server | generated tools | PRESERVE + HEADER-LOSS | pass-through |
| 16 | Composio | GMAIL_FETCH_EMAILS | PRESERVE + OMIT-END (inferred) | pass-through |
| 16 | Composio | SLACK_FETCH_CONVERSATION_HISTORY | PRESERVE + OMIT-END (inferred) | pass-through |
| 16 | Composio | GITHUB_FIND_PULL_REQUESTS | could not determine | other |
| 16 | Composio | GITHUB_LIST_REPOSITORY_ISSUES | could not determine | other |
| 17 | Zapier MCP | execute_zapier_read_action | SILENT-CAP (inferred) | no signal / cap |
| 18 | Pipedream | github-search-issues-and-pull-requests | AUTO-PAG to cap, then SILENT-CAP | no signal / cap |
| 18 | Pipedream | gmail-find-email | AUTO-PAG to cap, then SILENT-CAP | no signal / cap |
| 19 | Arcade | Slack.ListConversations etc. | AUTO-PAG + cursor | every page |
| 19 | Arcade | Gmail.ListEmails | SILENT-CAP | no signal / cap |
| 19 | Arcade | Gmail.SearchThreads | EXPLICIT-END | explicit |
| 19 | Arcade | Jira.SearchIssuesWithJql | EXPLICIT-END (`is_last_page: true`) | explicit |
| 20 | ACI.dev | GITHUB__LIST_ISSUES | PRESERVE + HEADER-LOSS (= no signal) | no signal / cap |
| 20 | ACI.dev | GMAIL__MESSAGES_LIST | PRESERVE | pass-through |
| 20 | ACI.dev | SLACK__CONVERSATIONS_LIST | PRESERVE | pass-through |
| 21 | Klavis AI | gmail_search_emails | SILENT-CAP | no signal / cap |
| 21 | Klavis AI | jira_search | PRESERVE/TOTAL-ONLY | total only |
| 22 | LangChain GitHub | get_issues | AUTO-PAG | every page |
| 22 | LangChain GitHub | search_issues_and_prs | SILENT-CAP | no signal / cap |
| 22 | LangChain GitHub | search_code | NL-NOTE without continuation | NL note |
| 23 | LangChain Jira | jql search | SILENT-CAP | no signal / cap |
| 24 | LangChain Slack | SlackGetMessage | SILENT-CAP | no signal / cap |
| 24 | LangChain Slack | SlackGetChannel | AUTO-PAG | every page |
| 25 | LangChain Gmail | GmailSearch | SILENT-CAP | no signal / cap |
| 26 | LlamaIndex | Gmail search_messages | SILENT-CAP | no signal / cap |
| 26 | LlamaIndex | Notion search_data | SILENT-CAP | no signal / cap |
| 26 | LlamaIndex | Jira jira_issues_query | SILENT-CAP | no signal / cap |
| 26 | LlamaIndex | Slack fetch_channels | SILENT-CAP | no signal / cap |
| 27 | CrewAI | GithubSearchTool | SILENT-CAP | no signal / cap |
| 27 | CrewAI | SerperDevTool | SILENT-CAP | no signal / cap |
| 28 | Google ADK | Spanner execute_sql | OMIT-END (truncation flag only when truncated) | omission |
| 28 | Google ADK | OpenAPIToolset RestApiTool | PRESERVE + HEADER-LOSS | pass-through |
| 29 | OpenAI Agents SDK | MCP tool adapter | PRESERVE | pass-through |
| 29 | OpenAI Agents SDK | FileSearchTool | retrieval, not pagination | other |

## Totals (intermediary tools)

| Row | Tools |
|---|---|
| Explicit end value | 3 |
| End by omitting a field | 7 |
| Total only | 2 |
| Natural-language note | 2 |
| No signal or silent cap | 21 |
| Returns or fetches every page | 5 |
| Passes the upstream body through | 16 |
| Other or undetermined | 5 |
| **Tools** | **61** |

Against the old column (3, 6, 2, 3, 21, 4, 12, 3; total 54), four rows change. Omission is 7 not 6; NL note is 2 not 3, because the Drive line is a keyed token line present only when more rows exist; every page is 5 not 4; pass-through is 16 not 12, with each Speakeasy product, each Composio and ACI body tool and the ADK and OpenAI adapters counted. Other is 5 not 3, adding Stainless Code Mode and FileSearchTool. The server column (42 tools) is unchanged. It matches the vendor notes' takeaway: 12, 10, 8, 6 and 5 rows, plus one tool that returns every page.

These are judgment calls; another reader could reasonably merge or split some entries. The rule above is written down so that the count can be redone.

## Server tools (42)

The paper's 42 server tools are the classified rows of the evidence table in `notes-vendor-and-reference-servers.md` (Key Question 1), counted as in that file's takeaway:

| Category in the paper | Code in the notes | Rows |
|---|---|---|
| No signal or silent cap | E | 12 |
| Explicit end value | A, including Grafana's heuristic `hasMore` and Atlassian after its June fix | 10 |
| End by omitting a field | B, two of them inferred | 8 |
| Total only | C | 6 |
| Natural-language note | D, including Azure's placeholder row | 5 |
| Returns every page | X (Neon) | 1 |
| **Tools** | | **42** |

A row can name a group of tools read together, such as GitHub's `search_*` tools or Neon's list tools. Atlassian's `searchJiraIssuesUsingJql` has three rows, one per observed state: the March 2026 row and the row after the June fix are counted, and the August regression row (coded "False A") is not. Stripe's remote `stripe_api_read`, which could not be determined ("?"), is not counted. The table therefore has 44 classified rows, 42 of them counted.
