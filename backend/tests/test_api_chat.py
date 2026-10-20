import pytest
import io
from unittest.mock import patch, MagicMock, AsyncMock


def test_chat_send_text_happy_path(api_client):
    mock_graph_result = {
        "reply_text": "Red Saree ₹599 mein available hai.",
        "reply_tts_text": "रेड साड़ी 599 रुपये में उपलब्ध है।",
        "reply_image_url": "https://img.com/red.jpg",
        "reply_price": 599,
        "reply_product_options": None,
        "listing_finalized": False,
        "listing_broadcast_caption": None,
        "listing_broadcast_caption_tts": None,
        "listing_product_name": None,
        "listing_category": None,
        "reply_purchase_intent_detected": False,
        "reply_order_id": None,
        "reply_confirmed_product_name": None,
        "reply_confirmed_product_price": None,
        "reply_confirmed_product_is_unlisted": False,
        "reply_handoff_triggered": False,
        "trace_logs": [{"agent": "CustomerAgent", "action": "Search"}],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result) as mock_invoke:
        response = api_client.post(
            "/api/v1/chat/send",
            data={
                "text_message": "Red Saree",
                "whatsapp_number": "whatsapp:+919876543210",
                "active_mode": "customer"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Contract fields validation
        assert data["text"] == "Red Saree ₹599 mein available hai."
        assert data["image_url"] == "https://img.com/red.jpg"
        assert data["price"] == 599
        assert data["product_options"] is None
        assert data["voice_fallback"] is False
        assert data["audio"] is not None
        assert data["listing_finalized"] is False
        assert data["broadcast_caption"] is None
        assert data["broadcast_audio"] is None
        assert data["purchase_intent_detected"] is False
        assert data["order_id"] is None
        assert data["confirmed_product_name"] is None
        assert data["confirmed_product_price"] is None
        assert data["confirmed_product_is_unlisted"] is False
        assert data["handoff_triggered"] is False

        # Verify orchestrator invocation state
        mock_invoke.assert_called_once()
        invoked_state = mock_invoke.call_args[0][0]
        assert invoked_state["raw_input"] == "Red Saree"
        assert invoked_state["whatsapp_number"] == "whatsapp:+919876543210"
        assert invoked_state["active_mode"] == "customer"
        assert invoked_state["input_type"] == "text"


def test_chat_send_listing_finalized_broadcast(api_client):
    mock_graph_result = {
        "reply_text": "Ho gaya Didi! Kurti ₹499 me live post ho gaya hai.",
        "reply_tts_text": "हो गया दीदी!",
        "reply_image_url": "https://img.com/kurti.jpg",
        "reply_price": 499,
        "reply_product_options": None,
        "listing_finalized": True,
        "listing_broadcast_caption": "🌸 *Cotton Kurti* @ ₹499! Order now!",
        "listing_broadcast_caption_tts": "कॉटन कुर्ती 499 रुपये में",
        "listing_product_name": "Cotton Kurti",
        "listing_category": "kurtis",
        "reply_purchase_intent_detected": False,
        "reply_order_id": None,
        "reply_confirmed_product_name": None,
        "reply_confirmed_product_price": None,
        "reply_confirmed_product_is_unlisted": False,
        "reply_handoff_triggered": False,
        "trace_logs": [],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result):
        response = api_client.post(
            "/api/v1/chat/send",
            data={
                "text_message": "haan post kar do",
                "whatsapp_number": "whatsapp:+919876543210",
                "active_mode": "reseller"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["listing_finalized"] is True
        assert data["broadcast_caption"] == "🌸 *Cotton Kurti* @ ₹499! Order now!"
        assert data["broadcast_audio"] is not None
        assert data["listing_product_name"] == "Cotton Kurti"
        assert data["listing_category"] == "kurtis"


def test_chat_send_purchase_intent_detected(api_client):
    mock_graph_result = {
        "reply_text": "Order notify kar diya!",
        "reply_tts_text": "ऑर्डर नोटिफाई कर दिया",
        "reply_image_url": None,
        "reply_price": None,
        "reply_product_options": None,
        "listing_finalized": False,
        "listing_broadcast_caption": None,
        "listing_broadcast_caption_tts": None,
        "listing_product_name": None,
        "listing_category": None,
        "reply_purchase_intent_detected": True,
        "reply_order_id": "ORD-9999",
        "reply_confirmed_product_name": "Silk Saree",
        "reply_confirmed_product_price": 750,
        "reply_confirmed_product_is_unlisted": False,
        "reply_handoff_triggered": False,
        "trace_logs": [],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result):
        response = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "isko order kar do", "active_mode": "customer"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["purchase_intent_detected"] is True
        assert data["order_id"] == "ORD-9999"
        assert data["confirmed_product_name"] == "Silk Saree"
        assert data["confirmed_product_price"] == 750


def test_chat_send_options_picker(api_client):
    options = [
        {"name": "Option 1", "price": 400, "base_image_url": "https://img1"},
        {"name": "Option 2", "price": 500, "base_image_url": "https://img2"},
    ]
    mock_graph_result = {
        "reply_text": "Options mile hain:",
        "reply_tts_text": "ऑप्शंस मिले हैं",
        "reply_image_url": None,
        "reply_price": None,
        "reply_product_options": options,
        "listing_finalized": False,
        "listing_broadcast_caption": None,
        "listing_broadcast_caption_tts": None,
        "listing_product_name": None,
        "listing_category": None,
        "reply_purchase_intent_detected": False,
        "reply_order_id": None,
        "reply_confirmed_product_name": None,
        "reply_confirmed_product_price": None,
        "reply_confirmed_product_is_unlisted": False,
        "reply_handoff_triggered": False,
        "trace_logs": [],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result):
        response = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "sarees", "active_mode": "reseller"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["product_options"] == options


def test_chat_send_empty_input_defaults_to_hello(api_client):
    mock_graph_result = {
        "reply_text": "Namaste didi",
        "reply_tts_text": "नमस्ते",
        "trace_logs": [],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result) as mock_invoke:
        response = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": ""}
        )

        assert response.status_code == 200
        mock_invoke.assert_called_once()
        invoked_state = mock_invoke.call_args[0][0]
        assert invoked_state["raw_input"] == "hello"


def test_chat_send_voice_note_pipeline(api_client):
    audio_content = b"fake-webm-audio-bytes"
    audio_file = ("test_note.webm", io.BytesIO(audio_content), "audio/webm")

    mock_graph_result = {
        "reply_text": "Voice note processed",
        "reply_tts_text": "वॉइस नोट",
        "trace_logs": [],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result) as mock_invoke:
        response = api_client.post(
            "/api/v1/chat/send",
            data={"active_mode": "reseller"},
            files={"audio_file": audio_file}
        )

        assert response.status_code == 200
        mock_invoke.assert_called_once()
        invoked_state = mock_invoke.call_args[0][0]
        assert invoked_state["input_type"] == "voice"
        assert invoked_state["raw_input"] == "transcribed audio text"


def test_chat_send_voice_note_transcription_failure(api_client):
    audio_content = b"corrupted-audio-bytes"
    audio_file = ("bad.webm", io.BytesIO(audio_content), "audio/webm")

    with patch("backend.api.chat_router.convert_to_wav", side_effect=Exception("ffmpeg decode failed")):
        response = api_client.post(
            "/api/v1/chat/send",
            files={"audio_file": audio_file}
        )

        assert response.status_code == 500
        assert "Voice note transcoding or transcription failed" in response.json()["detail"]


def test_chat_send_orchestrator_failure_returns_500(api_client):
    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", side_effect=RuntimeError("Graph node error")):
        response = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "crash test"}
        )

        assert response.status_code == 500
        assert "Graph node error" in response.json()["detail"]


def test_chat_send_streams_websocket_trace_logs(api_client):
    mock_log = {"agent": "GrowthAgent", "action": "Coaching", "latency_ms": 120}
    mock_graph_result = {
        "reply_text": "Sales report ready",
        "reply_tts_text": "सेल्स रिपोर्ट",
        "trace_logs": [mock_log],
    }

    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=mock_graph_result), \
         patch("backend.api.chat_router.manager.broadcast", new_callable=AsyncMock) as mock_broadcast:

        response = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "weekly sales"}
        )

        assert response.status_code == 200
        mock_broadcast.assert_called_once_with(mock_log)
