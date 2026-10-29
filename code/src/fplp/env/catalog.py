"""Generic vocabulary and row generators for the mock API.

Domains are deliberately generic (office supplies, household goods, support tickets).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

CUSTOMERS = [
    "Avery Lin", "Jordan Patel", "Morgan Reyes", "Casey Okafor", "Riley Novak", "Quinn Larsen",
    "Taylor Brooks", "Skyler Haddad", "Rowan Ito", "Emerson Dube", "Harper Silva", "Logan Weiss",
]

ORDER_ITEMS = [
    "Desk lamp", "USB-C cable", "A5 notebook", "Water bottle", "Office chair", "Monitor stand",
    "Wireless mouse", "Backpack", "Coffee mug", "Extension cord", "Whiteboard markers",
    "Bookshelf", "Keyboard", "Phone charger", "Desk fan", "Stapler", "Paper shredder",
    "File folders", "Webcam", "Headphones", "Printer paper", "Bike lock", "Umbrella",
    "Wall clock", "Lunch box", "Plant pot", "Doormat", "Towel set", "Picture frame", "Tape dispenser",
]
# Used only by the lookup task, so the looked-up item is unique in its result set.
LOOKUP_ITEMS = [
    "Standing desk mat", "Cable management tray", "Laptop riser", "Label printer",
    "Desk organizer set", "Footrest",
]
# "refunded" is reserved for controlled placement by the filtered_count task.
ORDER_STATUSES = ["delivered", "shipped", "processing", "cancelled"]

PRODUCT_QUERIES = {
    "lamp": "Lighting", "cable": "Electronics", "notebook": "Stationery", "chair": "Furniture",
    "bottle": "Kitchen", "charger": "Electronics", "backpack": "Bags", "monitor": "Electronics",
}
BRANDS = ["Arden", "Bexley", "Corvo", "Dalton", "Fenwick", "Garrow", "Halden", "Ivers"]
ADJECTIVES = ["compact", "heavy-duty", "portable", "classic", "slim", "adjustable", "foldable", "basic"]
COLORS = ["black", "white", "gray", "blue", "green", "red"]

TICKET_SUBJECTS = [
    "Cannot reset password", "Invoice shows wrong amount", "Delivery delayed",
    "Item arrived damaged", "Wrong item received", "Refund not received", "Account locked",
    "Discount code not working", "Change delivery address", "Missing part in package",
    "Charged twice", "Cannot update payment method", "Order stuck in processing",
    "Request for invoice copy", "Product question", "Cancel subscription",
]
PRIORITIES = ["low", "normal", "high"]

START_DATE = date(2026, 9, 30)


def _dates_desc(rng: random.Random, n: int) -> list[str]:
    d, out = START_DATE, []
    for _ in range(n):
        out.append(d.isoformat())
        d -= timedelta(days=rng.randint(0, 4))
    return out


def _ids(rng: random.Random, prefix: str, n: int, lo: int = 10000, hi: int = 99999) -> list[str]:
    return [f"{prefix}-{x}" for x in rng.sample(range(lo, hi), n)]


def orders(rng: random.Random, n: int, customer: str) -> list[dict]:
    ids, dates = _ids(rng, "ORD", n), _dates_desc(rng, n)
    return [
        {
            "order_id": ids[i],
            "customer": customer,
            "date": dates[i],
            "item": rng.choice(ORDER_ITEMS),
            "amount": round(rng.uniform(8, 250), 2),
            "status": rng.choice(ORDER_STATUSES),
        }
        for i in range(n)
    ]


def products(rng: random.Random, n: int, query: str) -> list[dict]:
    """Products whose names all contain `query`; prices are at least $20."""
    skus, models = _ids(rng, "SKU", n), rng.sample(range(100, 1000), n)
    return [
        {
            "sku": skus[i],
            "name": f"{rng.choice(BRANDS)} {rng.choice(ADJECTIVES)} {query} "
            f"({rng.choice(COLORS)}, model {models[i]})",
            "category": PRODUCT_QUERIES[query],
            "price": round(rng.uniform(20, 200), 2),
            "in_stock": rng.random() < 0.6,
        }
        for i in range(n)
    ]


def tickets(rng: random.Random, n: int, status: str) -> list[dict]:
    ids, dates = _ids(rng, "TCK", n, lo=1000), _dates_desc(rng, n)
    return [
        {
            "ticket_id": ids[i],
            "status": status,
            "priority": rng.choice(PRIORITIES),
            "subject": rng.choice(TICKET_SUBJECTS),
            "created": dates[i],
        }
        for i in range(n)
    ]
