"""Task builders: question, target query, controlled result set, and gold answer.

Needs all pages: filtered_count, oldest_date, exists, export_all, count_out_of_stock, count_high_priority.
Satisfied by page 1: name_one, lookup (answer on page 1).

- Counts are filtered ("orders with status refunded"), so no total count, note, or placeholder
  row gives the answer away without fetching.
- Count tasks show 1-3 matches on page 1 in every extent (a one-page set gets no later matches).
- The lookup question states that the order is unique, so page 1 is enough to answer it.
- Exists alternates "yes" and "no" across its occurrences within each cell. A "yes" sits past page 1, so answering
  without fetching is right only by luck; justified correctness (metrics) catches the luck.
- Needs-all questions come in a neutral phrasing (default, no "all"/"total") and an explicit
  one, so the word "all" can be tested as a cue instead of confounding every condition.
- Each tool carries at least two task types, so task and tool are not confounded.
- No task needs long arithmetic: a protocol check showed a sum over up to 100 amounts measured
  arithmetic, not pagination (one model retrieved every row in 33 of 40 episodes and gave the right
  total in 4), so it was
  replaced by the oldest order date, which always sits on the last page.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from fplp.conditions import Condition
from fplp.env import catalog
from fplp.signals.formats import Extent


@dataclass(frozen=True)
class Gold:
    answer_type: str  # count | amount | date | yes_no | id_set | sku_any
    value: int | float | str | list | None
    accepted: tuple[str, ...] = ()
    # Row indices the answer depends on; None means every row (counts, exports, a "no").
    # Justified correctness checks that these rows were retrieved, so a valid shortcut (jumping to
    # the last page for the oldest order, stopping once a qualifying product is found) counts.
    evidence: tuple[int, ...] | None = None


@dataclass
class EpisodeSpec:
    condition: Condition
    question: str
    target_tool: str
    target_args: dict
    rows: list[dict]
    gold: Gold
    short_first_page: int  # first-page size under the more_short extent

    @property
    def first_page_size(self) -> int:
        if self.condition.extent is Extent.MORE_SHORT:
            return self.short_first_page
        return min(self.condition.page_limit, len(self.rows))


def _positions(rng: random.Random, n: int, limit: int, region: str, k: int) -> list[int]:
    """Pick k row indices on page 1 or on later pages.

    Page-1 indices stay below limit // 2 so they remain on page 1 under a short first page.
    When the whole set fits on one page (the last_* extents), "later" falls back to the
    second half of the set.
    """
    if region == "page1":
        pool = range(min(limit // 2, n))
    elif n > limit:
        pool = range(limit, n)
    else:
        pool = range(n // 2, n)
    return rng.sample(list(pool), min(k, len(pool)))


def _ask(c: Condition, neutral: str, explicit: str) -> str:
    return explicit if c.phrasing == "explicit" else neutral


def _mark(rng, rows, n, limit, key, value) -> None:
    """Set rows[i][key] = value at 1-3 page-1 indices and, when later pages exist, 2-5 later ones.

    A one-page set gets no "later" matches: otherwise they would land on its only page, and page 1
    of a real last page would show 3-8 matches against 1-3 on page 1 of a longer set, so the
    extents would differ in page-1 content as well as in the signal (amendment 1)."""
    k1, k2 = rng.randint(1, 3), rng.randint(2, 5)
    first = set(_positions(rng, n, limit, "page1", k1))
    later = set(_positions(rng, n, limit, "later", k2)) if n > limit else set()
    for i in first | later:
        rows[i][key] = value


def _filtered_count(rng, n, limit, c):
    customer = rng.choice(catalog.CUSTOMERS)
    rows = catalog.orders(rng, n, customer)
    _mark(rng, rows, n, limit, "status", "refunded")
    gold = Gold("count", sum(r["status"] == "refunded" for r in rows))
    question = _ask(
        c,
        f'How many of {customer}\'s orders have the status "refunded"?',
        f'Across all of {customer}\'s orders, how many have the status "refunded"?',
    )
    return question, "list_orders", {"customer": customer}, rows, gold


def _oldest_date(rng, n, limit, c):
    customer = rng.choice(catalog.CUSTOMERS)
    rows = catalog.orders(rng, n, customer)
    # Orders come newest first, so the oldest is the last row: on the last page.
    gold = Gold("date", min(r["date"] for r in rows), evidence=(n - 1,))
    question = _ask(
        c,
        f"What is the date of {customer}'s oldest order?",
        f"Across all of {customer}'s orders, what is the date of the oldest one?",
    )
    return question, "list_orders", {"customer": customer}, rows, gold


def _exists(rng, n, limit, c):
    query = rng.choice(list(catalog.PRODUCT_QUERIES))
    rows = catalog.products(rng, n, query)
    yes = c.variant % 2 == 0  # alternates within every cell, so yes and no balance
    evidence = None
    if yes:
        (i,) = _positions(rng, n, limit, "later", 1)
        rows[i]["price"] = rng.choice([9.99, 12.49, 14.99])
        evidence = (i,)
    question = _ask(
        c,
        f'Is there a product matching "{query}" that costs less than $15? Answer yes or no.',
        f'Check all products matching "{query}": is there one that costs less than $15? Answer yes or no.',
    )
    return question, "search_products", {"query": query}, rows, Gold("yes_no", "yes" if yes else "no", evidence=evidence)


def _export_all(rng, n, limit, c):
    rows = catalog.tickets(rng, n, "open")
    gold = Gold("id_set", sorted(r["ticket_id"] for r in rows))
    question = _ask(
        c,
        "List the IDs of the open support tickets.",
        "List the IDs of all open support tickets.",
    )
    return question, "list_tickets", {"status": "open"}, rows, gold


def _count_out_of_stock(rng, n, limit, c):
    query = rng.choice(list(catalog.PRODUCT_QUERIES))
    rows = catalog.products(rng, n, query)
    for r in rows:
        r["in_stock"] = True
    _mark(rng, rows, n, limit, "in_stock", False)
    gold = Gold("count", sum(not r["in_stock"] for r in rows))
    question = _ask(
        c,
        f'How many products matching "{query}" are out of stock?',
        f'Across all products matching "{query}", how many are out of stock?',
    )
    return question, "search_products", {"query": query}, rows, gold


def _count_high_priority(rng, n, limit, c):
    rows = catalog.tickets(rng, n, "open")
    for r in rows:
        r["priority"] = rng.choice(["low", "normal"])
    _mark(rng, rows, n, limit, "priority", "high")
    gold = Gold("count", sum(r["priority"] == "high" for r in rows))
    question = _ask(
        c,
        "How many open support tickets have high priority?",
        "Across all open support tickets, how many have high priority?",
    )
    return question, "list_tickets", {"status": "open"}, rows, gold


def _name_one(rng, n, limit, c):
    query = rng.choice(list(catalog.PRODUCT_QUERIES))
    rows = catalog.products(rng, n, query)
    for i in _positions(rng, n, limit, "page1", 2):
        rows[i]["in_stock"] = True
    accepted = tuple(r["sku"] for r in rows if r["in_stock"])
    question = f'Name one product matching "{query}" that is currently in stock. Give its SKU.'
    return question, "search_products", {"query": query}, rows, Gold("sku_any", None, accepted)


def _lookup(rng, n, limit, c):
    customer = rng.choice(catalog.CUSTOMERS)
    rows = catalog.orders(rng, n, customer)
    item = rng.choice(catalog.LOOKUP_ITEMS)
    (i,) = _positions(rng, n, limit, "page1", 1)
    rows[i]["item"] = item
    # The question states that the order is unique, so page 1 answers it: without that, checking
    # later pages for a second such order was a reasonable reading (amendment 1).
    question = f"{customer} has exactly one order for a {item.lower()}. What was the amount of that order?"
    return question, "list_orders", {"customer": customer}, rows, Gold("amount", rows[i]["amount"])


BUILDERS = {
    "filtered_count": _filtered_count,
    "oldest_date": _oldest_date,
    "exists": _exists,
    "export_all": _export_all,
    "count_out_of_stock": _count_out_of_stock,
    "count_high_priority": _count_high_priority,
    "name_one": _name_one,
    "lookup": _lookup,
}


def build_episode(c: Condition) -> EpisodeSpec:
    rng = random.Random(f"{c.seed}:{c.task_type}:{c.item}")
    limit = c.page_limit
    # Draw every size up front, in a fixed order, so the rows that follow are identical
    # across signal forms for a given extent.
    n_multi = rng.randint(2 * limit + 1, 5 * limit)
    n_short = rng.randint(max(1, limit // 2), max(1, limit - 1))
    short_first = rng.randint(max(1, limit * 6 // 10), max(1, limit * 9 // 10))
    n = {
        Extent.MORE_FULL: n_multi,
        Extent.MORE_SHORT: n_multi,
        Extent.LAST_FULL: limit,
        Extent.LAST_SHORT: n_short,
    }[c.extent]
    question, tool, args, rows, gold = BUILDERS[c.task_type](rng, n, limit, c)
    return EpisodeSpec(c, question, tool, args, rows, gold, short_first)
