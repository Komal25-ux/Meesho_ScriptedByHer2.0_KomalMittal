import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key


def test_root_endpoint(api_client):
    response = api_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["service"] == "Sakhi API Gateway"
    assert data["version"] == "2.5"
    assert data["docs"] == "/docs"


def test_health_endpoint(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "supabase" in data
    assert "environment" in data


def test_tts_greeting_reseller_mode(api_client):
    response = api_client.get("/api/v1/tts/greeting?mode=reseller")
    assert response.status_code == 200
    data = response.json()
    assert "Namaste Sunita didi" in data["text"]
    assert data["audio"] is not None


def test_tts_greeting_customer_mode(api_client):
    response = api_client.get("/api/v1/tts/greeting?mode=customer")
    assert response.status_code == 200
    data = response.json()
    assert "Namaste! Main Sakhi hu" in data["text"]
    assert data["audio"] is not None


def test_tts_greeting_unknown_mode_fallback(api_client):
    # Unknown mode should fall back to reseller greeting
    response = api_client.get("/api/v1/tts/greeting?mode=unknown")
    assert response.status_code == 200
    data = response.json()
    assert "Namaste Sunita didi" in data["text"]


def test_system_trigger_return_happy_path(api_client):
    phone = "whatsapp:+919876543210"
    order_id = "ORD-404"
    product_name = "Yellow Saree"

    mock_outreach = {
        "reply_text": "Namaste! Order ORD-404 Yellow Saree return ke baare me poochhna tha.",
        "reply_tts_text": "नमस्ते! आर्डर ORD-404",
        "reply_image_url": None,
    }

    with patch("backend.api.chat_router.run_returns_proactive_outreach", return_value=mock_outreach) as mock_run_ret, \
         patch("backend.api.chat_router.manager.broadcast", new_callable=AsyncMock) as mock_broadcast:

        response = api_client.post(
            "/api/v1/system/trigger-return",
            data={
                "whatsapp_number": phone,
                "order_id": order_id,
                "product_name": product_name
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["text"] == mock_outreach["reply_text"]
        assert data["audio"] is not None
        assert data["image_url"] is None
        assert data["voice_fallback"] is False

        mock_run_ret.assert_called_once_with(phone, order_id, product_name)
        mock_broadcast.assert_called_once()
        broadcast_call = mock_broadcast.call_args[0][0]
        assert broadcast_call["agent"] == "ReturnsAgent"
        assert broadcast_call["action"] == "Proactive Return Outreach (System Triggered)"


def test_system_trigger_return_default_form_values(api_client):
    mock_outreach = {
        "reply_text": "Outreach default",
        "reply_tts_text": "आउटरीच",
        "reply_image_url": None,
    }

    with patch("backend.api.chat_router.run_returns_proactive_outreach", return_value=mock_outreach) as mock_run_ret, \
         patch("backend.api.chat_router.manager.broadcast", new_callable=AsyncMock):

        # Omit form fields to test default parameters
        response = api_client.post("/api/v1/system/trigger-return")

        assert response.status_code == 200
        mock_run_ret.assert_called_once_with(
            "whatsapp:+919876543210", "104", "Red Cotton Kurti"
        )


def test_system_trigger_return_failure_returns_500(api_client):
    with patch("backend.api.chat_router.run_returns_proactive_outreach", side_effect=ValueError("Lookup DB error")):
        response = api_client.post(
            "/api/v1/system/trigger-return",
            data={"order_id": "ERR-1"}
        )

        assert response.status_code == 500
        assert "Lookup DB error" in response.json()["detail"]


def test_chat_history_happy_path(api_client):
    response = api_client.get("/api/v1/chat/history?whatsapp_number=whatsapp:+919876543210&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    assert len(data["history"]) == 2
    assert data["history"][0]["role"] == "user"


def test_chat_history_db_error_returns_500(api_client):
    from backend.db.supabase_client import db_client
    with patch.object(db_client, "get_conversation_history", side_effect=Exception("DB connection timeout")):
        response = api_client.get("/api/v1/chat/history?whatsapp_number=whatsapp:+919876543210")
        assert response.status_code == 500
        assert "DB connection timeout" in response.json()["detail"]
