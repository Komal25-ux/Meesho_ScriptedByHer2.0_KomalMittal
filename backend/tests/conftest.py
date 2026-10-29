"""Shared test setup.

Layout (see TESTING.md for the reasoning):
  unit/        pure rules - pricing, parsing, matching, limits; no app objects
  components/  one agent or graph node at a time, on the fakes in support/
  journeys/    whole conversations through the compiled graph
  adapters/    the edges: session store, database client, Gemini client, audio
  api/         HTTP behaviour - contract, validation, limits, security
"""
import os
import socket

import pytest
from hypothesis import HealthCheck, settings as hypothesis_settings

# Settings are read at import time, so these must be set before any backend
# module loads. The Supabase values are fake on purpose: the client is
# created, every real call is blocked below, and tests swap in fakes.
os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "mock-service-key")
os.environ.setdefault("GEMINI_API_KEY", "mock-gemini-key")
os.environ.setdefault("GEMINI_API_KEY_FALLBACK", "mock-gemini-fallback")
os.environ.setdefault("GEMINI_API_KEY_FALLBACK_2", "mock-gemini-fallback-2")
os.environ["SESSION_STORE"] = "memory"

# CI runs the property tests with a fixed seed so a failure always
# reproduces; locally they explore new examples on every run.
hypothesis_settings.register_profile("ci", derandomize=True, deadline=None, max_examples=200)
hypothesis_settings.register_profile("dev", deadline=None, suppress_health_check=[HealthCheck.too_slow])
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A test that reaches for the real Gemini, Sarvam or Supabase fails loudly."""
    def refuse(self, *args, **kwargs):
        raise RuntimeError(f"Network access attempted during a test: {args}")
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture(autouse=True)
def fresh_session_state(monkeypatch):
    """Every test starts with no conversation state at all."""
    from backend.core import session
    monkeypatch.setattr(session, "store", session.InMemorySessionStore())


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    from backend.api.limits import ip_limiter, session_limiter
    ip_limiter.reset()
    session_limiter.reset()


@pytest.fixture
def sakhi(monkeypatch):
    """The real graph and agents running on fakes: scripted Gemini, scripted
    classifiers and an in-memory Supabase holding the test catalog."""
    from backend.tests.support.catalog import CATALOG
    from backend.tests.support.harness import install
    return install(monkeypatch, CATALOG)


@pytest.fixture
def voice(monkeypatch):
    """Sarvam and ffmpeg replaced: speech-to-text hears `voice.heard`, and
    every synthesized voice note is recorded."""
    class Voice:
        heard = "laal saree dikhao"
        spoken = []

        async def synthesize(self, text):
            self.spoken.append(text)
            return f"audio:{text}".encode()

        async def to_wav(self, path):
            return path + ".wav"

        async def transcribe(self, path):
            return self.heard

    fake = Voice()
    fake.spoken = []
    monkeypatch.setattr("backend.api.chat_router.synthesize_speech", fake.synthesize)
    monkeypatch.setattr("backend.api.chat_router.convert_to_wav", fake.to_wav)
    monkeypatch.setattr("backend.api.chat_router.transcribe_audio", fake.transcribe)
    return fake


@pytest.fixture
def api_client(sakhi, voice):
    """The FastAPI app over the fakes, called through HTTP."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)
