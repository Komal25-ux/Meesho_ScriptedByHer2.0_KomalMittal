"""Health, the greeting voice note, and the simulated return event."""
import pytest

from backend.core.gemini_utils import ReturnsAgentResponse
from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key

from backend.tests.support.sessions import SESSION_A, SESSION_B


def test_health_reports_whether_the_database_is_real(api_client, monkeypatch):
    assert api_client.get("/health").json()["supabase"] == "connected"

    monkeypatch.setattr("backend.main.db_client.is_mock", lambda: True)
    assert api_client.get("/health").json()["supabase"] == "mock_mode"


@pytest.mark.parametrize("mode, opening", [
    ("reseller", "Namaste Sunita didi!"),
    ("customer", "Namaste! Main Sakhi hu."),
    ("admin", "Namaste Sunita didi!"),    # an unknown mode gets the reseller greeting
])
def test_the_greeting_matches_the_pane_and_is_spoken_in_devanagari(api_client, voice, mode, opening):
    body = api_client.get(f"/api/v1/tts/greeting?mode={mode}").json()

    assert body["text"].startswith(opening)
    assert voice.spoken and all(not any("a" <= c <= "z" for c in t.lower()) for t in voice.spoken)


def trigger(api_client, session=SESSION_A, **fields):
    return api_client.post("/api/v1/system/trigger-return", data={"session_id": session, **fields})


def test_a_return_event_messages_that_sessions_buyer_and_starts_the_funnel(api_client, sakhi):
    sakhi.gemini.will_return(ReturnsAgentResponse, ui_text="Namaste! Kya dikkat aayi?", tts_text="नमस्ते!",
                             suggests_alternative=False)

    body = trigger(api_client, order_id="ORD-7", product_name="Pink Cotton Kurti").json()

    assert body["text"] == "Namaste! Kya dikkat aayi?"
    assert body["image_url"] is None and body["voice_fallback"] is False
    assert PENDING_RETURNS[_pending_key(SESSION_A, "customer")]["order_id"] == "ORD-7"
    assert _pending_key(SESSION_B, "customer") not in PENDING_RETURNS
    assert sakhi.db.returns[-1]["resolution"] == "awaiting_customer_response"


def test_a_return_event_without_fields_uses_the_demo_order(api_client, sakhi):
    trigger(api_client)

    assert PENDING_RETURNS[_pending_key(SESSION_A, "customer")]["order_id"] == "104"


def test_a_return_event_needs_a_session(api_client):
    assert api_client.post("/api/v1/system/trigger-return", data={"order_id": "104"}).status_code == 422


def test_a_return_event_that_cannot_be_saved_is_a_503(api_client, sakhi):
    sakhi.db.fail("save_return")

    assert trigger(api_client).status_code == 503


def test_a_return_event_that_fails_unexpectedly_reveals_nothing(api_client, monkeypatch):
    def broken(*_):
        raise ValueError("Lookup DB error at row 7")
    monkeypatch.setattr("backend.api.chat_router.run_returns_proactive_outreach", broken)

    response = trigger(api_client)

    assert response.status_code == 500
    assert "Lookup DB error" not in response.text


def test_the_old_chat_history_endpoint_is_gone(api_client):
    # It returned any reseller's conversation to whoever knew the number.
    assert api_client.get("/api/v1/chat/history?whatsapp_number=whatsapp:+919876543210").status_code == 404
