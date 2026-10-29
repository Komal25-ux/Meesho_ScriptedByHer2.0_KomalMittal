"""Configuration that must refuse to run, rather than run wrongly."""
import pytest

from backend.config import Settings, settings
from backend.db.supabase_client import SupabaseDB


@pytest.fixture
def no_database(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")


def test_production_refuses_to_start_without_a_database(monkeypatch, no_database):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="production"):
        SupabaseDB()


def test_development_without_a_database_runs_on_the_demo_catalog(monkeypatch, no_database):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    assert SupabaseDB().is_mock()


def test_production_refuses_to_keep_conversations_in_memory(monkeypatch):
    from backend.core import session
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SESSION_STORE", "memory")

    with pytest.raises(RuntimeError, match="production"):
        session._build_store()


def test_an_unknown_session_store_is_a_startup_error(monkeypatch):
    from backend.core import session
    monkeypatch.setattr(settings, "SESSION_STORE", "redis")

    with pytest.raises(ValueError, match="redis"):
        session._build_store()


@pytest.mark.parametrize("cors, frontend, allowed", [
    ("https://a.example,https://b.example", "http://localhost:5173",
     ["http://localhost:5173", "https://a.example", "https://b.example"]),
    (" https://a.example/ , ,", "https://a.example", ["https://a.example"]),   # spaces, trailing slash, blanks, duplicates
    ("", "", []),
])
def test_allowed_origins_are_cleaned_and_always_include_the_frontend(cors, frontend, allowed):
    assert Settings(CORS_ORIGINS=cors, FRONTEND_URL=frontend).allowed_origins == allowed
