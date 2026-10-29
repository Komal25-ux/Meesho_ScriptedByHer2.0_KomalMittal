from datetime import datetime, timedelta, timezone

import pytest

from backend.core import session
from backend.core.session import InMemorySessionStore, SessionSlot, SupabaseSessionStore

from backend.tests.support.fakes import FakeSessionTable


KEY = "0b7e3d4c-2a1f-4e6d-8c5b-9a0f1e2d3c4b::customer"


@pytest.fixture
def db():
    return FakeSessionTable()


@pytest.fixture
def store(db):
    return SupabaseSessionStore(db, ttl=timedelta(hours=24))


# ── The copy rule ────────────────────────────────────────────────────

@pytest.mark.parametrize("make_store", [InMemorySessionStore, lambda: SupabaseSessionStore(FakeSessionTable(), timedelta(hours=1))])
def test_changing_a_value_read_from_the_store_does_not_change_the_stored_value(make_store):
    s = make_store()
    s.set(KEY, "shown_product_ids", ["SKU_001"])

    shown = s.get(KEY, "shown_product_ids")
    shown.append("SKU_002")

    assert s.get(KEY, "shown_product_ids") == ["SKU_001"]


def test_memory_store_rejects_values_a_jsonb_column_could_not_hold():
    with pytest.raises(TypeError):
        InMemorySessionStore().set(KEY, "shown_product_ids", {"SKU_001"})


# ── Persistence ──────────────────────────────────────────────────────

def test_state_written_before_a_restart_is_there_after_it(db):
    before_restart = SupabaseSessionStore(db, timedelta(hours=24))
    before_restart.set(KEY, "pending_returns", {"order_id": "104", "stage": "awaiting_grievance"})

    after_restart = SupabaseSessionStore(db, timedelta(hours=24))

    assert after_restart.get(KEY, "pending_returns") == {"order_id": "104", "stage": "awaiting_grievance"}


def test_a_turn_on_one_instance_sees_what_another_instance_wrote(db):
    instance_1 = SupabaseSessionStore(db, timedelta(hours=24))
    instance_2 = SupabaseSessionStore(db, timedelta(hours=24))

    instance_1.set(KEY, "last_requested_category", "sarees")
    instance_2.begin([KEY])
    try:
        assert instance_2.get(KEY, "last_requested_category") == "sarees"
    finally:
        instance_2.end([KEY])


def test_expired_rows_are_not_returned(db, store):
    store.set(KEY, "fresh_broadcast_lock", True)
    db.rows[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

    assert store.get(KEY, "fresh_broadcast_lock") is None


def test_every_write_pushes_the_expiry_forward(db, store):
    store.set(KEY, "last_requested_category", "sarees")
    first_expiry = db.rows[0]["expires_at"]

    store.set(KEY, "last_requested_category", "kurtis")

    assert db.rows[0]["expires_at"] >= first_expiry
    assert len(db.rows) == 1  # upsert, not a second row


# ── The per-turn cache ───────────────────────────────────────────────

def test_a_turn_reads_the_database_once_however_many_slots_it_checks(db, store):
    store.set(KEY, "pending_listings", {"selling_price": 599})

    store.begin([KEY])
    try:
        for slot in ("pending_returns", "pending_listings", "pending_selections", "last_viewed_product"):
            store.get(KEY, slot)
    finally:
        store.end([KEY])

    assert db.selects == 1


def test_writes_inside_a_turn_are_visible_to_later_reads_in_the_same_turn(db, store):
    store.begin([KEY])
    try:
        store.get(KEY, "pending_selections")  # loads the (empty) session into the cache
        store.set(KEY, "pending_selections", {"agent": "customer", "options": []})
        store.delete(KEY, "pending_selections")
        assert store.get(KEY, "pending_selections") is None

        store.set(KEY, "last_viewed_product", {"name": "Red Banarasi Silk Saree"})
        assert store.get(KEY, "last_viewed_product") == {"name": "Red Banarasi Silk Saree"}
    finally:
        store.end([KEY])

    assert db.selects == 1


def test_nothing_is_cached_between_turns(db, store):
    store.begin([KEY])
    store.get(KEY, "pending_returns")
    store.end([KEY])

    # Another instance starts a return while this one is idle.
    db.rows.append({
        "session_key": KEY, "slot": "pending_returns", "value": {"stage": "awaiting_grievance"},
        "updated_at": "", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })

    store.begin([KEY])
    try:
        assert store.get(KEY, "pending_returns") == {"stage": "awaiting_grievance"}
    finally:
        store.end([KEY])


def test_reads_outside_a_turn_always_go_to_the_database(db, store):
    store.get(KEY, "pending_returns")
    store.get(KEY, "pending_returns")

    assert db.selects == 2


def test_an_overlapping_turn_on_the_same_session_keeps_the_cache_until_both_end(db, store):
    store.begin([KEY])  # first message still being processed
    store.begin([KEY])  # user sent a second one
    store.get(KEY, "pending_returns")
    store.end([KEY])    # first finishes

    store.get(KEY, "pending_returns")
    assert db.selects == 1

    store.end([KEY])
    store.get(KEY, "pending_returns")
    assert db.selects == 2


def test_the_database_store_refuses_to_clear_a_slot_for_every_session(store):
    with pytest.raises(NotImplementedError):
        store.clear("pending_returns")


# ── SessionSlot behaves like the dict it replaced ────────────────────

def test_session_slot_dict_operations(monkeypatch):
    monkeypatch.setattr(session, "store", InMemorySessionStore())
    slot = SessionSlot("pending_listings")

    assert slot.get(KEY) is None
    assert slot.get(KEY, "fallback") == "fallback"
    assert KEY not in slot
    with pytest.raises(KeyError):
        slot[KEY]

    slot[KEY] = {"selling_price": 599}
    assert KEY in slot
    assert slot[KEY] == {"selling_price": 599}

    assert slot.pop(KEY) == {"selling_price": 599}
    assert slot.pop(KEY, "already gone") == "already gone"
    assert KEY not in slot


def test_session_slot_has_no_setdefault():
    # setdefault hands back a value to mutate in place; with a database
    # behind the slot those mutations would be silently lost.
    assert not hasattr(SessionSlot("shown_product_ids"), "setdefault")


def test_session_turn_covers_both_modes_and_releases_them_on_error(monkeypatch):
    calls = []

    class Recorder(InMemorySessionStore):
        def begin(self, keys):
            calls.append(("begin", list(keys)))

        def end(self, keys):
            calls.append(("end", list(keys)))

    monkeypatch.setattr(session, "store", Recorder())
    sid = "0b7e3d4c-2a1f-4e6d-8c5b-9a0f1e2d3c4b"

    with pytest.raises(RuntimeError):
        with session.session_turn(sid):
            raise RuntimeError("graph failed mid-turn")

    expected = [f"{sid}::reseller", f"{sid}::customer"]
    assert calls == [("begin", expected), ("end", expected)]
