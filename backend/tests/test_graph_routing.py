import pytest
from unittest.mock import patch, MagicMock

from backend.core.orchestrator import (
    route_pending_return,
    route_pending,
    route_pending_selection,
    route_fresh_context_lock,
    route_decision,
    check_pending_approval,
    check_pending_selection,
    check_fresh_context_lock,
    check_pending_return,
    detect_intent,
)
from backend.core.session import (
    PENDING_LISTINGS,
    PENDING_SELECTIONS,
    FRESH_BROADCAST_LOCK,
    LAST_VIEWED_PRODUCT,
    PENDING_RETURNS,
)
from backend.core.state import _pending_key
from backend.core.gemini_utils import (
    IntentRouter,
    CatalogCaptionResponse,
    CustomerAgentResponse,
    ReturnsAgentResponse,
)


# ── ROUTER FUNCTION TESTS ─────────────────────────────────────
def test_route_functions():
    assert route_pending_return({"pending_return_route": "handled"}) == "handled"
    assert route_pending_return({}) == "not_pending"

    assert route_pending({"pending_route": "finalize"}) == "finalize"
    assert route_pending({}) == "not_pending"

    assert route_pending_selection({"pending_selection_route": "catalog"}) == "catalog"
    assert route_pending_selection({}) == "not_pending"

    assert route_fresh_context_lock({"context_lock_route": "handled"}) == "handled"
    assert route_fresh_context_lock({}) == "not_locked"

    assert route_decision({"detected_intent": "CATALOG"}) == "CATALOG"
    assert route_decision({}) == "GENERAL"


# ── PENDING APPROVAL GATE ─────────────────────────────────────
def test_check_pending_approval_no_draft(make_state):
    state = make_state(raw_input="haan post kar do", active_mode="reseller")
    res = check_pending_approval(state)
    assert res["pending_route"] == "not_pending"


def test_check_pending_approval_approved(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "reseller")
    PENDING_LISTINGS[key] = {
        "matched_product_name": "Kurti",
        "selling_price": 500,
        "cost": 300,
        "listing_payload": {"product_name": "Kurti", "selling_price_inr": 500},
        "base_image_url": "https://img.com/k.jpg",
    }
    state = make_state(raw_input="haan kar do", whatsapp_number=phone, active_mode="reseller")

    with patch("backend.core.orchestrator.classify_approval_intent", return_value="approve"):
        res = check_pending_approval(state)
        assert res["pending_route"] == "finalize"
        # Draft remains in PENDING_LISTINGS until finalize_catalog_listing consumes it
        assert key in PENDING_LISTINGS


def test_check_pending_approval_modified_price(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "reseller")
    PENDING_LISTINGS[key] = {
        "matched_product_name": "Kurti",
        "selling_price": 500,
        "cost": 300,
        "listing_payload": {"product_name": "Kurti", "selling_price_inr": 500},
        "base_image_url": "https://img.com/k.jpg",
    }
    state = make_state(raw_input="price 650 kar do", whatsapp_number=phone, active_mode="reseller")

    mock_caption = CatalogCaptionResponse(
        ui_text="Updated caption", tts_text="Updated tts", product_name_tts="कुर्ती"
    )

    with patch("backend.core.orchestrator.classify_approval_intent", return_value="modify"), \
         patch("backend.core.orchestrator.generate_whatsapp_caption", return_value=mock_caption):
        res = check_pending_approval(state)
        assert res["pending_route"] == "price_updated"
        assert PENDING_LISTINGS[key]["selling_price"] == 650
        assert res["reply_price"] == 650


def test_check_pending_approval_abandoned_on_new_request(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "reseller")
    PENDING_LISTINGS[key] = {"matched_product_name": "Kurti", "selling_price": 500, "cost": 300}
    state = make_state(raw_input="kuch aur dikhao", whatsapp_number=phone, active_mode="reseller")

    with patch("backend.core.orchestrator.classify_approval_intent", return_value="new_request"):
        res = check_pending_approval(state)
        assert res["pending_route"] == "not_pending"
        # Draft must be popped on abandon
        assert key not in PENDING_LISTINGS


# ── PENDING SELECTION GATE ────────────────────────────────────
def test_check_pending_selection_matched(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "reseller")
    PENDING_SELECTIONS[key] = {
        "agent": "catalog",
        "options": [{"name": "Blue Kurti"}, {"name": "Red Kurti"}]
    }
    state = make_state(raw_input="Blue Kurti", whatsapp_number=phone, active_mode="reseller")

    res = check_pending_selection(state)
    assert res["pending_selection_route"] == "catalog"
    # PENDING_SELECTIONS should be consumed
    assert key not in PENDING_SELECTIONS


def test_check_pending_selection_unmatched(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "reseller")
    PENDING_SELECTIONS[key] = {
        "agent": "catalog",
        "options": [{"name": "Blue Kurti"}, {"name": "Red Kurti"}]
    }
    state = make_state(raw_input="kuch aur dikhao", whatsapp_number=phone, active_mode="reseller")

    res = check_pending_selection(state)
    assert res["pending_selection_route"] == "not_pending"
    assert key not in PENDING_SELECTIONS


# ── FRESH CONTEXT LOCK GATE ───────────────────────────────────
def test_check_fresh_context_lock_buying_interest(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "customer")
    FRESH_BROADCAST_LOCK[key] = True
    LAST_VIEWED_PRODUCT[key] = {
        "product_id": "SKU-1",
        "name": "Silk Saree",
        "suggested_selling_price_inr": 699,
        "base_image_url": "https://img.com/s.jpg",
    }
    state = make_state(raw_input="I want to buy", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text="Ji zaroor! Silk Saree ₹699 mein available hai.",
        tts_text="जी ज़रूर! सिल्क साड़ी 699 रुपये में उपलब्ध है।",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=True,
    )

    with patch("backend.core.orchestrator.classify_buying_interest", return_value=True), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp):
        res = check_fresh_context_lock(state)
        assert res["context_lock_route"] == "handled"
        assert res["reply_image_url"] == "https://img.com/s.jpg"
        assert key not in FRESH_BROADCAST_LOCK  # One-shot


def test_check_fresh_context_lock_no_buying_interest_disarms(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "customer")
    FRESH_BROADCAST_LOCK[key] = True
    LAST_VIEWED_PRODUCT[key] = {"name": "Silk Saree"}
    state = make_state(raw_input="namaste didi", whatsapp_number=phone, active_mode="customer")

    with patch("backend.core.orchestrator.classify_buying_interest", return_value=False):
        res = check_fresh_context_lock(state)
        assert res["context_lock_route"] == "not_locked"
        # One-shot: popped even when not showing buying interest
        assert key not in FRESH_BROADCAST_LOCK


# ── PENDING RETURN GATE ───────────────────────────────────────
def test_check_pending_return_grievance_size_issue(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "customer")
    PENDING_RETURNS[key] = {
        "order_id": "ORD-1",
        "product_name": "Blue Kurti",
        "stage": "awaiting_grievance",
        "original_product": {"name": "Blue Kurti", "sizes": ["M", "L"]},
    }
    state = make_state(raw_input="size chhota hai", whatsapp_number=phone, active_mode="customer")

    mock_resp = ReturnsAgentResponse(
        ui_text="Maaf kijiyega! Kya aap larger size exchange chahte hain?",
        tts_text="माफ़ कीजियेगा!",
        suggests_alternative=True,
    )

    with patch("backend.core.orchestrator.classify_return_grievance", return_value="size_issue"), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp):
        res = check_pending_return(state)
        assert res["pending_return_route"] == "handled"
        assert key in PENDING_RETURNS
        assert PENDING_RETURNS[key]["stage"] == "awaiting_confirmation"
        assert PENDING_RETURNS[key]["grievance"] == "size_issue"


def test_check_pending_return_confirmation_accept(make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    key = _pending_key(phone, "customer")
    PENDING_RETURNS[key] = {
        "order_id": "ORD-1",
        "product_name": "Blue Kurti",
        "stage": "awaiting_confirmation",
        "grievance": "size_issue",
        "proposed_alternative": {"name": "Blue Kurti L"},
    }
    state = make_state(raw_input="theek hai exchange kar do", whatsapp_number=phone, active_mode="customer")

    mock_resp = ReturnsAgentResponse(
        ui_text="Exchange confirm ho gaya!",
        tts_text="एक्सचेंज कन्फर्म हो गया!",
        suggests_alternative=False,
    )

    with patch("backend.core.orchestrator.classify_exchange_confirmation", return_value="accept"), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp):
        res = check_pending_return(state)
        assert res["pending_return_route"] == "handled"
        assert res["reply_handoff_triggered"] is True
        # Terminal: popped from PENDING_RETURNS
        assert key not in PENDING_RETURNS


# ── INTENT DETECTION ROUTER ───────────────────────────────────
def test_detect_intent_fast_path_triggers(make_state, mock_db_orchestrator):
    # Catalog trigger prefix
    state_cat = make_state(raw_input="ye item whatsapp group mein share karna hai: Kurti")
    assert detect_intent(state_cat)["detected_intent"] == "CATALOG"

    # Customer trigger prefix
    state_cust = make_state(raw_input="mujhe ye wala item pasand hai, iski details batao: Saree")
    assert detect_intent(state_cust)["detected_intent"] == "CUSTOMER"


def test_detect_intent_llm_classification(make_state, mock_db_orchestrator):
    state = make_state(raw_input="weekly sales report", active_mode="reseller")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="GROWTH")):
        assert detect_intent(state)["detected_intent"] == "GROWTH"


def test_detect_intent_customer_mode_safety_clamp(make_state, mock_db_orchestrator):
    # Customer chatting directly attempting to trigger reseller-only agent is clamped to GENERAL
    state = make_state(raw_input="sales report", active_mode="customer")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="GROWTH")):
        assert detect_intent(state)["detected_intent"] == "GENERAL"

    state_cat = make_state(raw_input="catalog listing", active_mode="customer")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")):
        assert detect_intent(state_cat)["detected_intent"] == "GENERAL"


def test_detect_intent_returns_clamped_to_customer(make_state, mock_db_orchestrator):
    # RETURNS intent must be clamped to CUSTOMER
    state = make_state(raw_input="mujhe item return karna hai", active_mode="customer")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="RETURNS")):
        assert detect_intent(state)["detected_intent"] == "CUSTOMER"
