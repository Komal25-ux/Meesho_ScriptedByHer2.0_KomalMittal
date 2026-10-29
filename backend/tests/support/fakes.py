"""Hand-written stand-ins for Gemini, Supabase and the LLM classifiers.

Each fake keeps a record of what it was asked, so a test can check the
outcome (what was saved, what the model was told) instead of re-stating
which internal functions were called.
"""
import copy
import itertools
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from backend.errors import DependencyUnavailable


class ScriptedGemini:
    """Structured Gemini calls (generate_structured_with_fallback).

    Replies are queued per response schema and handed out in order. A call
    with nothing queued returns None - what the real helper returns once
    every model and key has failed - so an empty script means "Gemini is
    down" and the code under test takes its deterministic path."""

    def __init__(self):
        self._queued: Dict[type, Deque[Any]] = defaultdict(deque)
        self.prompts: Dict[type, List[str]] = defaultdict(list)

    def will_return(self, schema: type, **fields) -> None:
        self._queued[schema].append(schema(**fields))

    def structured(self, prompt: str, schema: type):
        self.prompts[schema].append(prompt)
        queue = self._queued[schema]
        return queue.popleft() if queue else None

    def last_prompt(self, schema: type) -> str:
        return self.prompts[schema][-1]


class Classifiers:
    """Fixed answers for the small LLM classifiers, so an agent test decides
    exactly which branch runs. Defaults are the answers that change nothing:
    not a follow-up, no category, no interest, a plain return, a decline."""

    def __init__(self):
        self.approval = "new_request"
        self.attribute_followup = False
        self.category: Optional[str] = None
        self.buying_interest = False
        self.grievance = "hard_return"
        self.exchange = "decline"
        self.calls: List[tuple] = []

    def classify_approval_intent(self, text, pending):
        self.calls.append(("approval", text))
        return self.approval

    def classify_attribute_followup(self, text, product_name):
        self.calls.append(("attribute_followup", text))
        return self.attribute_followup

    def extract_category_intent(self, text, last_category):
        self.calls.append(("category", text))
        if self.category == "same":
            return last_category
        return self.category

    def classify_buying_interest(self, text, product_name):
        self.calls.append(("buying_interest", text))
        return self.buying_interest

    def classify_return_grievance(self, text, product_name):
        self.calls.append(("grievance", text))
        return self.grievance

    def classify_exchange_confirmation(self, text):
        self.calls.append(("exchange", text))
        return self.exchange


class QueryVector(list):
    """What the fake embedding call returns: a normal 768-float list that
    also carries the text it was made from, so FakeSupabase can search on
    words instead of on similarity."""

    def __init__(self, text: str):
        super().__init__([0.0] * 768)
        self.text = text


def fake_embedding(text: str, task_type: str = "retrieval_query", output_dimensionality: int = 768) -> List[float]:
    return QueryVector(text) if text and text.strip() else []


def _words(text: str) -> set:
    return set(re.findall(r"[a-z]+", text.lower()))


class FakeSupabase:
    """The parts of SupabaseDB the agents use, over in-memory tables.

    Search is word overlap between the query and a product's name, category,
    colours and material, which is enough to make "red saree" find the red
    saree. A category browse returns everything in the category, like the
    real match_products_filtered with its threshold dropped."""

    RESELLER = {
        "id": "reseller-1", "whatsapp_number": "whatsapp:+919876543210", "name": "Sunita Didi",
        "location": "Kanpur, UP", "language": "hi", "dialect": "hindi",
    }

    def __init__(self, products: List[dict]):
        self.products = {p["product_id"]: copy.deepcopy(p) for p in products}
        self.listings: List[dict] = []
        self.orders: List[dict] = []
        self.returns: List[dict] = []
        self.events: List[dict] = []
        self.turns: List[dict] = []
        self._down: set = set()
        self._ids = itertools.count(1)
        self.clock = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.clock

    # failure injection ----------------------------------------------------
    def fail(self, *methods: str) -> None:
        """Make these methods raise DependencyUnavailable from now on."""
        self._down.update(methods)

    def recover(self) -> None:
        self._down.clear()

    def _check(self, method: str) -> None:
        if method in self._down:
            raise DependencyUnavailable(f"fake {method} is down")

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    # readers --------------------------------------------------------------
    def is_mock(self) -> bool:
        return False

    def get_or_create_reseller(self, whatsapp_number: str) -> dict:
        self._check("get_or_create_reseller")
        return dict(self.RESELLER, whatsapp_number=whatsapp_number)

    def get_reseller_profile(self, reseller_id: str) -> dict:
        self._check("get_reseller_profile")
        return {"monthly_target_inr": 10000, "preferred_categories": ["sarees", "kurtis"]}

    def get_product_by_name(self, name: str) -> Optional[dict]:
        self._check("get_product_by_name")
        wanted = (name or "").strip().lower()
        for product in self.products.values():
            if product["name"].lower() == wanted:
                return copy.deepcopy(product)
        return None

    def match_products(self, query_embedding, threshold=0.3, limit=3, category_filter=None, exclude_ids=None) -> list:
        self._check("match_products")
        query = _words(getattr(query_embedding, "text", ""))
        excluded = set(exclude_ids or [])
        scored = []
        for order, product in enumerate(self.products.values()):
            if product["product_id"] in excluded:
                continue
            if category_filter and product.get("category") != category_filter:
                continue
            haystack = _words(" ".join([
                product["name"], product.get("category", ""), " ".join(product.get("colors") or []),
                product.get("material") or "",
            ]))
            overlap = len(query & haystack)
            if overlap or category_filter:
                scored.append((-overlap, order, product))
        scored.sort(key=lambda item: item[:2])
        return [copy.deepcopy(product) for _, _, product in scored[:limit]]

    def get_listing(self, reseller_id: str, product_id: str) -> Optional[dict]:
        self._check("get_listing")
        matches = [l for l in self.listings if l["product_id"] == product_id]
        if not matches:
            return None
        newest = matches[-1]
        return {"id": newest["id"], "selling_price_inr": newest["selling_price_inr"]}

    # arranging state ------------------------------------------------------
    def list_product(self, product_id: str, price: int) -> dict:
        """As if the reseller had already listed this product at `price`."""
        product = self.products[product_id]
        return self.save_listing({
            "reseller_id": self.RESELLER["id"], "product_id": product_id, "product_name": product["name"],
            "category": product["category"], "selling_price_inr": price, "cost_price_inr": product["meesho_cost_inr"],
        })

    # writers --------------------------------------------------------------
    def save_listing(self, listing: dict) -> dict:
        self._check("save_listing")
        row = dict(listing, id=self._new_id("listing"))
        self.listings.append(row)
        return dict(row)

    def find_recent_order(self, session_id: str, product_id: str, within) -> Optional[dict]:
        self._check("find_recent_order")
        cutoff = self.now() - within
        matches = [o for o in self.orders
                   if o.get("session_id") == session_id and o["product_id"] == product_id and o["ordered_at"] >= cutoff]
        return dict(matches[-1]) if matches else None

    def save_order(self, order: dict) -> dict:
        """Like the real table: client_message_id is unique, and a repeat
        returns the order that id already created."""
        self._check("save_order")
        key = order.get("client_message_id")
        existing = next((o for o in self.orders if key and o.get("client_message_id") == key), None)
        if existing:
            return dict(existing)
        row = dict(order, id=self._new_id("order"), ordered_at=self.now())
        self.orders.append(row)
        return dict(row)

    def save_return(self, record: dict) -> dict:
        self._check("save_return")
        row = dict(record, id=self._new_id("return"))
        self.returns.append(row)
        return dict(row)

    def log_agent_event(self, event: dict) -> None:
        self.events.append(event)

    def save_conversation_turn(self, turn: dict) -> None:
        self.turns.append(turn)

    # what SupabaseDB exposes and the fixture swaps in -----------------------
    METHODS = [
        "is_mock", "get_or_create_reseller", "get_reseller_profile", "get_product_by_name", "match_products",
        "get_listing", "save_listing", "find_recent_order", "save_order", "save_return", "log_agent_event",
        "save_conversation_turn",
    ]


class FakeSessionTable:
    """Just enough of supabase-py's query builder for session_state: rows in
    a list, filters applied for real, and a count of SELECTs so a test can
    tell a cache hit from a database read."""

    def __init__(self):
        self.rows = []
        self.selects = 0

    def table(self, name):
        assert name == "session_state"
        return _Query(self)


class _Query:
    def __init__(self, db):
        self.db = db
        self.op = None
        self.payload = None
        self.filters = []

    def select(self, _columns):
        self.op = "select"
        return self

    def upsert(self, row, on_conflict):
        assert on_conflict == "session_key,slot"
        self.op, self.payload = "upsert", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r[column] == value)
        return self

    def gt(self, column, value):
        self.filters.append(lambda r: r[column] > value)
        return self

    def execute(self):
        matches = [r for r in self.db.rows if all(f(r) for f in self.filters)]
        if self.op == "select":
            self.db.selects += 1
            return _Result([{"slot": r["slot"], "value": r["value"]} for r in matches])
        if self.op == "delete":
            self.db.rows = [r for r in self.db.rows if r not in matches]
            return _Result([])
        key = (self.payload["session_key"], self.payload["slot"])
        self.db.rows = [r for r in self.db.rows if (r["session_key"], r["slot"]) != key]
        self.db.rows.append(dict(self.payload))
        return _Result([self.payload])


class _Result:
    def __init__(self, data):
        self.data = data
