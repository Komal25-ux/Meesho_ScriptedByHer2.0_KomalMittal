"""Conversation state that has to outlive a single /chat/send call.

Every turn is a fresh, stateless LangGraph invocation, so anything the next
turn needs - a draft awaiting approval, a return in progress, the product
being discussed - lives here, keyed by _pending_key(session_id, mode).

Each slot below reads like a dict, but the values live in a store, not in
this process:

- SupabaseSessionStore (whenever the database is configured): one row per
  (session key, slot) in the session_state table, with an expiry. State
  survives restarts and redeploys and is shared by every backend instance.
- InMemorySessionStore: local runs without Supabase, and the test suite.

Both stores hand back copies. A value read from a slot is a snapshot, so
changing it changes nothing until it is assigned back
(SLOT[key] = value). That is what makes the Supabase store correct, and the
in-memory store deliberately behaves the same so a missing write-back fails
in tests instead of only in production.
"""
import copy
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from backend.config import settings
from backend.core.state import _pending_key
from backend.db.supabase_client import db_client
from backend.errors import DependencyUnavailable

logger = logging.getLogger("sakhi-backend")

__all__ = [
    "PENDING_LISTINGS",
    "PENDING_SELECTIONS",
    "LAST_VIEWED_PRODUCT",
    "FRESH_BROADCAST_LOCK",
    "SHOWN_PRODUCT_IDS",
    "LAST_REQUESTED_CATEGORY",
    "PENDING_RETURNS",
    "session_turn",
]

_MODES = ("reseller", "customer")


class InMemorySessionStore:
    def __init__(self):
        self._rows: Dict[tuple, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str, slot: str) -> Optional[Any]:
        with self._lock:
            raw = self._rows.get((key, slot))
        return None if raw is None else json.loads(raw)

    def set(self, key: str, slot: str, value: Any) -> None:
        raw = json.dumps(value)  # same serialisability rule as a jsonb column
        with self._lock:
            self._rows[(key, slot)] = raw

    def delete(self, key: str, slot: str) -> None:
        with self._lock:
            self._rows.pop((key, slot), None)

    def clear(self, slot: str) -> None:
        with self._lock:
            for row_key in [k for k in self._rows if k[1] == slot]:
                del self._rows[row_key]

    def begin(self, keys: Iterable[str]) -> None:
        pass

    def end(self, keys: Iterable[str]) -> None:
        pass


class SupabaseSessionStore:
    """session_state rows, read through a cache that only exists for the
    length of a turn. Inside session_turn(), the first read of a session key
    loads all of its slots in one query and later reads are served from
    memory; writes go to the database immediately. Between turns nothing is
    cached, so a turn always starts from what the database holds - whichever
    instance wrote it."""

    TABLE = "session_state"

    def __init__(self, client, ttl: timedelta):
        self._client = client
        self._ttl = ttl
        self._lock = threading.Lock()
        self._active: Dict[str, int] = {}
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _slots(self, key: str) -> Dict[str, Any]:
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        now = datetime.now(timezone.utc).isoformat()
        try:
            res = (
                self._client.table(self.TABLE)
                .select("slot,value")
                .eq("session_key", key)
                .gt("expires_at", now)
                .execute()
            )
        except Exception as e:
            raise DependencyUnavailable("Reading session state failed") from e
        slots = {row["slot"]: row["value"] for row in (res.data or [])}
        with self._lock:
            if self._active.get(key):
                self._cache[key] = slots
        return slots

    def get(self, key: str, slot: str) -> Optional[Any]:
        return copy.deepcopy(self._slots(key).get(slot))

    def set(self, key: str, slot: str, value: Any) -> None:
        now = datetime.now(timezone.utc)
        try:
            self._client.table(self.TABLE).upsert(
                {
                    "session_key": key,
                    "slot": slot,
                    "value": value,
                    "updated_at": now.isoformat(),
                    "expires_at": (now + self._ttl).isoformat(),
                },
                on_conflict="session_key,slot",
            ).execute()
        except Exception as e:
            raise DependencyUnavailable("Writing session state failed") from e
        with self._lock:
            if key in self._cache:
                self._cache[key][slot] = copy.deepcopy(value)

    def delete(self, key: str, slot: str) -> None:
        try:
            self._client.table(self.TABLE).delete().eq("session_key", key).eq("slot", slot).execute()
        except Exception as e:
            raise DependencyUnavailable("Deleting session state failed") from e
        with self._lock:
            if key in self._cache:
                self._cache[key].pop(slot, None)

    def clear(self, slot: str) -> None:
        raise NotImplementedError("Refusing to wipe a slot for every live session in the database")

    def begin(self, keys: Iterable[str]) -> None:
        with self._lock:
            for key in keys:
                if not self._active.get(key):
                    self._cache.pop(key, None)
                self._active[key] = self._active.get(key, 0) + 1

    def end(self, keys: Iterable[str]) -> None:
        with self._lock:
            for key in keys:
                remaining = self._active.get(key, 0) - 1
                if remaining > 0:
                    self._active[key] = remaining
                else:
                    self._active.pop(key, None)
                    self._cache.pop(key, None)


def _build_store():
    choice = settings.SESSION_STORE or ("memory" if db_client.is_mock() else "supabase")
    if choice == "supabase":
        logger.info("Session state: Supabase table session_state")
        return SupabaseSessionStore(db_client.client, timedelta(hours=settings.SESSION_TTL_HOURS))
    if choice == "memory":
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("SESSION_STORE=memory is not allowed in production: state would be lost on restart")
        logger.warning("Session state: in-memory (lost on restart, not shared between instances)")
        return InMemorySessionStore()
    raise ValueError(f"Unknown SESSION_STORE {choice!r}; expected 'supabase' or 'memory'")


store = _build_store()


class SessionSlot:
    """One named piece of per-conversation state, used like a dict keyed by
    session key. Deliberately has no setdefault(): it returns a value meant
    to be mutated in place, which would never reach the store."""

    def __init__(self, name: str):
        self.name = name

    def get(self, key: str, default: Any = None) -> Any:
        value = store.get(key, self.name)
        return default if value is None else value

    def __getitem__(self, key: str) -> Any:
        value = store.get(key, self.name)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key: str) -> bool:
        return store.get(key, self.name) is not None

    def __setitem__(self, key: str, value: Any) -> None:
        store.set(key, self.name, value)

    def pop(self, key: str, default: Any = None) -> Any:
        value = store.get(key, self.name)
        if value is None:
            return default
        store.delete(key, self.name)
        return value

    def clear(self) -> None:
        store.clear(self.name)


@contextmanager
def session_turn(session_id: str):
    """Bracket one request's work on a conversation, both of its modes - a
    reseller turn that finalizes a listing also writes the customer side."""
    keys = [_pending_key(session_id, mode) for mode in _MODES]
    store.begin(keys)
    try:
        yield
    finally:
        store.end(keys)


# Catalog listings awaiting reseller approval, keyed by session + active_mode.
#
# Keying by session alone would mean Reseller and Customer mode share the same
# pending-approval slot (one browser tab drives both panes), so a draft
# awaiting confirmation in Reseller mode would bleed into Customer mode's
# chat. Namespacing the key by mode isolates them.
PENDING_LISTINGS = SessionSlot("pending_listings")

# A ProductGrid picker awaiting a selection, keyed exactly
# like PENDING_LISTINGS/PENDING_RETURNS. Written by run_catalog_agent /
# run_customer_agent when a vector search turns up 2-4 ambiguous SKU matches
# (see ProductGrid.jsx), and resolved by check_pending_selection on the next
# turn - the reseller/customer taps an option, which sends its exact product
# name back as the next message.
PENDING_SELECTIONS = SessionSlot("pending_selections")

# The last specific product a customer was grounded on
# (i.e. the last turn where run_customer_agent's Success Case fired for
# exactly one item), keyed exactly like the slots above. This app has no real
# cross-turn conversation memory - every /chat/send call is a stateless graph
# invocation - so without this, a natural follow-up confirmation like "isko
# order kar do" or "ye pack kardo" (which doesn't repeat the product name)
# has nothing to resolve against: that message's OWN vector search matches
# loosely against several unrelated catalog items (being a generic phrase
# with no product-specific words), which used to fall through to the
# Browsing Case and show a fresh picker - i.e. an infinite "here are some
# options" loop right when the customer was trying to confirm a purchase.
# This slot is the minimal fix: remember the one item most recently grounded,
# so Priority 2 has a real referent for "isko"/"ye"/"yehi" even when this
# turn's own search can't provide one.
LAST_VIEWED_PRODUCT = SessionSlot("last_viewed_product")

# One-shot flag: true for exactly the customer's VERY NEXT message after a
# reseller listing is finalized and broadcast into the Customer segment (see
# finalize_catalog_listing), false/absent every other turn. Backs the
# "Latest Context Lock": check_fresh_context_lock pops this (so it can never
# fire twice for the same broadcast) and, if this one message shows buying/
# detail interest, deterministically answers using the just-broadcast product
# instead of letting detect_intent's classifier or a fresh vector search
# route it into the ambiguous-match picker - the "reseller posts an item,
# customer immediately says 'I want to buy' and gets shown unrelated
# alternatives instead" bug. Keyed exactly like LAST_VIEWED_PRODUCT (in fact
# always set alongside it), so it only ever applies to the Customer segment.
FRESH_BROADCAST_LOCK = SessionSlot("fresh_broadcast_lock")

# Product IDs already shown to this session in the CURRENT category-scoped
# browse (see run_customer_agent / run_catalog_agent's category-strict
# pagination) - what "show more" excludes so a repeat request never repeats
# an item. Keyed like the slots above; cleared whenever the session's active
# category actually changes (see LAST_REQUESTED_CATEGORY).
SHOWN_PRODUCT_IDS = SessionSlot("shown_product_ids")

# The category this session is currently browsing, if any - lets a bare
# follow-up like "aur dikhao" ("show more") stay scoped to the same category
# without the customer having to repeat it every turn.
LAST_REQUESTED_CATEGORY = SessionSlot("last_requested_category")

# A return in progress awaiting the customer's next reply,
# keyed exactly like PENDING_LISTINGS (session + active_mode) so it
# never bleeds into the Reseller segment. Seeded by run_returns_proactive_outreach
# when the backend system webhook fires (see /api/v1/system/trigger-return) -
# this is the ONLY way a return ever starts. From there, the customer's
# free-text replies are intercepted here turn-by-turn (the graph has no
# persistent thread memory, so without this slot there would be no way to
# know "this customer is mid-return" by the time their next message arrives).
PENDING_RETURNS = SessionSlot("pending_returns")
