import os
import pytest
from unittest.mock import MagicMock

# Ensure required environment variables exist with mock defaults before any module imports
os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "mock-service-key")
os.environ.setdefault("GEMINI_API_KEY", "mock-gemini-key")
os.environ.setdefault("GEMINI_API_KEY_FALLBACK", "mock-gemini-fallback")
os.environ.setdefault("GEMINI_API_KEY_FALLBACK_2", "mock-gemini-fallback-2")

import socket

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Guard against any real external network calls during test execution."""
    def guarded_connect(self, *args, **kwargs):
        raise RuntimeError(f"Network access disabled during unit tests: connect attempted with {args}")
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture(autouse=True)
def reset_session_stores():
    """Clear in-memory session dictionaries before each test to prevent test leakage."""
    from backend.core import session
    session.PENDING_LISTINGS.clear()
    session.PENDING_SELECTIONS.clear()
    session.LAST_VIEWED_PRODUCT.clear()
    session.FRESH_BROADCAST_LOCK.clear()
    session.SHOWN_PRODUCT_IDS.clear()
    session.LAST_REQUESTED_CATEGORY.clear()
    session.PENDING_RETURNS.clear()
    yield
    session.PENDING_LISTINGS.clear()
    session.PENDING_SELECTIONS.clear()
    session.LAST_VIEWED_PRODUCT.clear()
    session.FRESH_BROADCAST_LOCK.clear()
    session.SHOWN_PRODUCT_IDS.clear()
    session.LAST_REQUESTED_CATEGORY.clear()
    session.PENDING_RETURNS.clear()


@pytest.fixture
def make_state():
    """Factory fixture for a standard SakhiState dict."""
    def _factory(**overrides):
        base = {
            "raw_input": "namaste",
            "whatsapp_number": "whatsapp:+919876543210",
            "active_mode": "reseller",
            "reseller_id": "reseller-123",
            "reseller_name": "Sunita Didi",
            "reseller_location": "Kanpur",
            "reseller_language": "hi",
            "reseller_dialect": "hindi",
            "detected_intent": "GENERAL",
            "intent_confidence": 1.0,
            "reply_text": "",
            "reply_tts_text": "",
            "reply_image_url": None,
            "reply_price": None,
            "reply_product_options": None,
            "trace_logs": [],
            "context_data": {},
            "listing_finalized": False,
            "listing_broadcast_caption": None,
            "listing_broadcast_caption_tts": None,
            "listing_product_name": None,
            "listing_category": None,
            "pending_route": None,
            "pending_selection_route": None,
            "context_lock_route": None,
            "pending_return_route": None,
        }
        base.update(overrides)
        return base
    return _factory


@pytest.fixture
def mock_db_orchestrator(monkeypatch):
    """Provides standard mock implementations for db_client methods invoked by orchestrator nodes."""
    from backend.db.supabase_client import db_client
    from unittest.mock import MagicMock

    monkeypatch.setattr(db_client, "get_or_create_reseller", lambda phone: {
        "id": "reseller-123",
        "name": "Sunita Didi",
        "location": "Kanpur",
        "language": "hi",
        "dialect": "hindi",
    })
    monkeypatch.setattr(db_client, "get_reseller_profile", lambda r_id: {
        "id": r_id,
        "commission_rate": 0.2,
    })
    monkeypatch.setattr(db_client, "save_conversation_turn", lambda payload: {"id": "turn-1"})
    monkeypatch.setattr(db_client, "log_agent_event", lambda payload: {"id": "log-1"})
    monkeypatch.setattr(db_client, "save_listing", lambda payload: {"id": "listing-1", **payload})
    monkeypatch.setattr(db_client, "save_order", lambda payload: {"id": "order-1", **payload})
    monkeypatch.setattr(db_client, "save_return", lambda payload: {"id": "return-1", **payload})
    monkeypatch.setattr(db_client, "is_product_listed", lambda r_id, p_id: True)
    monkeypatch.setattr(db_client, "get_listing_id", lambda r_id, p_id: "listing-1")
    return db_client


