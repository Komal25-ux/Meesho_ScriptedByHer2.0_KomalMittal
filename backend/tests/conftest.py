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
