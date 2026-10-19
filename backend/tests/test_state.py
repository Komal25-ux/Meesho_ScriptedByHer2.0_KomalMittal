import pytest
from backend.core.state import SakhiState, _pending_key


def test_pending_key_format():
    key = _pending_key("whatsapp:+919876543210", "reseller")
    assert key == "whatsapp:+919876543210::reseller"


def test_pending_key_isolation_by_user():
    key1 = _pending_key("whatsapp:+911111111111", "reseller")
    key2 = _pending_key("whatsapp:+912222222222", "reseller")
    assert key1 != key2


def test_pending_key_isolation_by_mode():
    phone = "whatsapp:+919876543210"
    reseller_key = _pending_key(phone, "reseller")
    customer_key = _pending_key(phone, "customer")
    assert reseller_key != customer_key
    assert reseller_key == f"{phone}::reseller"
    assert customer_key == f"{phone}::customer"


def test_pending_key_determinism():
    phone = "whatsapp:+919876543210"
    mode = "reseller"
    assert _pending_key(phone, mode) == _pending_key(phone, mode)


def test_sakhi_state_typed_dict():
    # Verify SakhiState can be initialized as a dictionary with expected keys
    state: SakhiState = {
        "raw_input": "namaste",
        "whatsapp_number": "whatsapp:+919876543210",
        "active_mode": "reseller",
        "reseller_id": "test-id",
        "reseller_name": "Sunita",
        "reseller_location": "Kanpur",
        "reseller_language": "hi",
        "reseller_dialect": "hindi",
        "detected_intent": "GENERAL",
        "intent_confidence": 1.0,
        "reply_text": "Namaste Didi!",
        "reply_tts_text": "नमस्ते दीदी!",
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
    assert state["raw_input"] == "namaste"
    assert state["active_mode"] == "reseller"
    assert state["detected_intent"] == "GENERAL"
