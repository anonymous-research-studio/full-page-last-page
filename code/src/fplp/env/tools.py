"""Tool schemas exposed to the agent, in a provider-neutral form.

Design defaults (see prereg):
- The page limit is stated, in the description and on the `limit` parameter, so a full
  page is recognizable as full. The limit arm hides it (`limit_stated=False`), as many real
  APIs do; the server still caps pages at the limit.
- Every list tool accepts both `cursor` and `page`, so every signal form is actionable.
- The documentation arm changes only whether the description says results are paginated.
  The `cursor` and `page` parameters exist in both arms, which is itself a weak cue. With the
  default description, the no-signal baseline is "documented pagination, no signal in the
  response", not an uncued one.
- The description says a cursor comes "from a previous response, when it includes one", so it
  does not promise a cursor in forms whose responses carry none. The "plain" wording (amendment 2,
  exploratory) drops "when it includes one", to test whether that clause acts as an end cue.
"""

from __future__ import annotations

TOOL_NAMES = ("list_orders", "search_products", "list_tickets", "get_ticket")
QUERY_ARG = {"list_orders": "customer", "search_products": "query", "list_tickets": "status"}
RESOURCE_PATHS = {"list_orders": "orders", "search_products": "products/search", "list_tickets": "tickets"}


def _paging_params(page_limit: int, documented: bool, limit_stated: bool, wording: str = "default") -> dict:
    if limit_stated:
        limit = {
            "type": "integer",
            "minimum": 1,
            "maximum": page_limit,
            "description": f"Maximum number of results to return (default {page_limit}, maximum {page_limit}).",
        }
    else:
        limit = {"type": "integer", "minimum": 1, "description": "Maximum number of results to return."}
    if not documented:
        return {"cursor": {"type": "string"}, "page": {"type": "integer", "minimum": 1}, "limit": limit}
    return {
        "cursor": {"type": "string", "description": "Cursor from a previous response, to fetch the next page."
                   if wording == "plain" else "Cursor from a previous response, when it includes one, to fetch "
                   "the next page."},
        "page": {"type": "integer", "minimum": 1, "description": "Page number to fetch (1-based)."},
        "limit": limit,
    }


def tool_schemas(page_limit: int, documented: bool, limit_stated: bool = True, wording: str = "default") -> list[dict]:
    """Return tools as {"name", "description", "parameters"}; clients convert to their own format."""
    paging = _paging_params(page_limit, documented, limit_stated, wording)
    cap = f" Returns at most {page_limit} results per call." if limit_stated else ""
    source = "from a previous response" if wording == "plain" else "from a previous response, when it includes one"
    note = f" Results are paginated: pass `cursor` ({source}) or `page` to fetch further results." if documented else ""

    def listing(name: str, summary: str, arg: str, arg_schema: dict) -> dict:
        return {
            "name": name,
            "description": f"{summary}{cap}{note}",
            "parameters": {
                "type": "object",
                "properties": {arg: arg_schema, **paging},
                "required": [arg],
            },
        }

    return [
        listing(
            "list_orders",
            "List a customer's orders, newest first.",
            "customer",
            {"type": "string", "description": "Customer's full name."},
        ),
        listing(
            "search_products",
            "Search the product catalog by keyword.",
            "query",
            {"type": "string", "description": "Search keyword."},
        ),
        listing(
            "list_tickets",
            "List support tickets with a given status, newest first.",
            "status",
            {"type": "string", "enum": ["open", "pending", "closed"], "description": "Ticket status."},
        ),
        {
            "name": "get_ticket",
            "description": "Get one support ticket by ID.",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string", "description": "Ticket ID, e.g. TCK-1042."}},
                "required": ["ticket_id"],
            },
        },
    ]
