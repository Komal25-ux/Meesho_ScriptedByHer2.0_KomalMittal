"""SupabaseDB (backend/db/supabase_client.py): what it asks Postgres for,
and what it does when Postgres doesn't answer.

The rule for failures: on the critical path an error is raised
(DependencyUnavailable -> 503), never turned into an empty or placeholder
result the agents would read as a real answer. The two telemetry writes are
the exception: a lost log line must not fail a buyer's turn.
"""
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from backend.db.supabase_client import SupabaseDB
from backend.errors import DependencyUnavailable

QUERY = [0.1] * 768


def db_over(client):
    db = SupabaseDB.__new__(SupabaseDB)  # skip __init__: no credentials needed
    db.client = client
    db._mock_orders = []
    return db


class Unreachable:
    def table(self, *_):
        raise ConnectionError("connection reset by peer")

    def rpc(self, *_args, **_kwargs):
        raise ConnectionError("connection reset by peer")


@pytest.fixture
def postgres():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [{"product_id": "SKU_007"}]
    return client


# ── failures ─────────────────────────────────────────────────────────

CRITICAL_CALLS = [
    ("get_or_create_reseller", ("whatsapp:+919876543210",)),
    ("get_reseller_profile", ("reseller-1",)),
    ("get_product_by_name", ("Red Banarasi Silk Saree",)),
    ("match_products", (QUERY,)),
    ("get_listing", ("reseller-1", "SKU_001")),
    ("find_recent_order", ("session-1", "SKU_001", timedelta(minutes=10))),
    ("save_listing", ({"product_id": "SKU_001"},)),
    ("save_order", ({"product_id": "SKU_001"},)),
    ("save_return", ({"reason": "size_issue"},)),
]


@pytest.mark.parametrize("method, args", CRITICAL_CALLS, ids=[name for name, _ in CRITICAL_CALLS])
def test_an_unreachable_database_is_raised_on_the_critical_path(method, args):
    with pytest.raises(DependencyUnavailable):
        getattr(db_over(Unreachable()), method)(*args)


@pytest.mark.parametrize("method", ["save_listing", "save_order", "save_return"])
def test_an_insert_that_returns_no_row_counts_as_a_failure(method):
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = []

    with pytest.raises(DependencyUnavailable):
        getattr(db_over(client), method)({"product_id": "SKU_001"})


@pytest.mark.parametrize("method, payload", [
    ("log_agent_event", {"event_type": "customer_rag"}),
    ("save_conversation_turn", {"role": "user", "content": "hi"}),
])
def test_telemetry_writes_never_fail_a_turn(method, payload):
    getattr(db_over(Unreachable()), method)(payload)  # must not raise


# ── product search ───────────────────────────────────────────────────

def test_a_plain_search_uses_the_unfiltered_function_with_the_callers_threshold(postgres):
    db_over(postgres).match_products(QUERY, threshold=0.3, limit=3)

    assert postgres.rpc.call_args[0] == ("match_products", {"query_embedding": QUERY, "match_threshold": 0.3, "match_count": 3})


def test_a_category_browse_filters_in_sql_drops_the_threshold_and_fetches_only_what_it_needs(postgres):
    db_over(postgres).match_products(QUERY, threshold=0.3, limit=4, category_filter="sarees",
                                     exclude_ids=["SKU_003", "SKU_001", "SKU_003"])

    name, params = postgres.rpc.call_args[0]
    assert name == "match_products_filtered"
    assert params == {"query_embedding": QUERY, "match_threshold": 0.0, "match_count": 4,
                      "category_filter": "sarees", "exclude_ids": ["SKU_001", "SKU_003"]}


def test_excluding_shown_items_without_a_category_keeps_the_threshold(postgres):
    db_over(postgres).match_products(QUERY, threshold=0.2, limit=4, exclude_ids=["SKU_001"])

    name, params = postgres.rpc.call_args[0]
    assert (name, params["category_filter"], params["match_threshold"]) == ("match_products_filtered", None, 0.2)


def test_rows_come_back_exactly_as_postgres_returned_them(postgres):
    assert db_over(postgres).match_products(QUERY, limit=4, category_filter="sarees") == [{"product_id": "SKU_007"}]


def test_a_real_search_with_no_query_returns_nothing_rather_than_demo_products(postgres):
    assert db_over(postgres).match_products([], limit=4) == []
    postgres.rpc.assert_not_called()


def test_the_exact_name_lookup_never_pulls_the_embedding_column(postgres):
    db_over(postgres).get_product_by_name("Red Banarasi Silk Saree")

    columns = postgres.table.return_value.select.call_args[0][0]
    assert "embedding" not in columns and "name" in columns


# ── orders ───────────────────────────────────────────────────────────

def order_db(inserted=None, existing=None):
    client = MagicMock()
    table = client.table.return_value
    table.insert.return_value.execute.return_value.data = inserted
    table.upsert.return_value.execute.return_value.data = inserted
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = existing
    return db_over(client), table


def test_an_order_with_a_message_id_is_upserted_ignoring_duplicates():
    db, table = order_db(inserted=[{"id": "o-1"}])

    assert db.save_order({"product_id": "SKU_001", "client_message_id": "m-1"}) == {"id": "o-1"}
    assert table.upsert.call_args.kwargs == {"on_conflict": "client_message_id", "ignore_duplicates": True}
    table.insert.assert_not_called()


def test_a_repeated_message_id_returns_the_order_already_stored():
    db, table = order_db(inserted=[], existing=[{"id": "o-original"}])

    assert db.save_order({"product_id": "SKU_001", "client_message_id": "m-1"}) == {"id": "o-original"}
    table.select.return_value.eq.assert_called_once_with("client_message_id", "m-1")


def test_an_order_without_a_message_id_is_a_plain_insert():
    db, table = order_db(inserted=[{"id": "o-2"}])

    assert db.save_order({"product_id": "SKU_001"}) == {"id": "o-2"}
    table.upsert.assert_not_called()


def test_the_recent_order_lookup_is_scoped_to_conversation_product_and_time(postgres):
    db_over(postgres).find_recent_order("session-1", "SKU_001", timedelta(minutes=10))

    chain = postgres.table.return_value.select.return_value
    chain.eq.assert_called_once_with("session_id", "session-1")
    chain.eq.return_value.eq.assert_called_once_with("product_id", "SKU_001")
    assert chain.eq.return_value.eq.return_value.gte.call_args[0][0] == "ordered_at"


# ── mock mode (local runs without Supabase) ──────────────────────────

@pytest.fixture
def mock_db():
    return db_over(None)


def test_mock_mode_serves_the_demo_catalog(mock_db):
    assert [p["product_id"] for p in mock_db.match_products([], limit=4)] == ["SKU_001", "SKU_002"]


@pytest.mark.parametrize("category, excluded, expected", [
    ("sarees", None, ["SKU_001"]),
    ("kurtis", ["SKU_002"], []),
    ("lehengas", None, []),
])
def test_mock_mode_applies_the_same_filters_as_the_sql(mock_db, category, excluded, expected):
    results = mock_db.match_products(QUERY, limit=4, category_filter=category, exclude_ids=excluded)
    assert [p["product_id"] for p in results] == expected


def test_mock_mode_also_refuses_a_duplicate_order(mock_db):
    first = mock_db.save_order({"product_id": "SKU_001", "client_message_id": "m-1", "session_id": "s"})
    again = mock_db.save_order({"product_id": "SKU_001", "client_message_id": "m-1", "session_id": "s"})

    assert again["id"] == first["id"]
    assert mock_db.find_recent_order("s", "SKU_001", timedelta(minutes=10))["id"] == first["id"]
