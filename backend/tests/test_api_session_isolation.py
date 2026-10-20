import pytest
from unittest.mock import patch

from backend.core.session import (
    PENDING_LISTINGS,
    PENDING_SELECTIONS,
    LAST_VIEWED_PRODUCT,
    PENDING_RETURNS,
)
from backend.core.state import _pending_key
from backend.core.gemini_utils import (
    IntentRouter,
    CatalogCaptionResponse,
    CustomerAgentResponse,
)


def test_api_cross_user_session_isolation(api_client):
    user_a = "whatsapp:+911111111111"
    user_b = "whatsapp:+912222222222"
    key_a = _pending_key(user_a, "reseller")
    key_b = _pending_key(user_b, "reseller")

    candidates_a = [
        {"product_id": "A1", "name": "Item A1", "suggested_selling_price_inr": 350, "meesho_cost_inr": 200},
        {"product_id": "A2", "name": "Item A2", "suggested_selling_price_inr": 380, "meesho_cost_inr": 220},
    ]
    candidates_b = [
        {"product_id": "B1", "name": "Item B1", "suggested_selling_price_inr": 750, "meesho_cost_inr": 500},
        {"product_id": "B2", "name": "Item B2", "suggested_selling_price_inr": 780, "meesho_cost_inr": 520},
    ]

    # ── User A Turn 1: Triggers picker options ──
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="sarees"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates_a):

        resp_a1 = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "Item A", "whatsapp_number": user_a, "active_mode": "reseller"}
        )
        assert resp_a1.status_code == 200
        assert resp_a1.json()["product_options"] is not None

    # ── User B Turn 1: Triggers picker options ──
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="kurtis"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates_b):

        resp_b1 = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "Item B", "whatsapp_number": user_b, "active_mode": "reseller"}
        )
        assert resp_b1.status_code == 200
        assert resp_b1.json()["product_options"] is not None

    # Assert distinct sessions created
    assert key_a in PENDING_SELECTIONS
    assert key_b in PENDING_SELECTIONS
    assert PENDING_SELECTIONS[key_a]["options"][0]["name"] == "Item A1"
    assert PENDING_SELECTIONS[key_b]["options"][0]["name"] == "Item B1"

    # ── User A Turn 2: User A selects Item A1 via API ──
    caption_a = CatalogCaptionResponse(ui_text="Draft A1", tts_text="ड्राफ्ट A1", product_name_tts="Item A1")
    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=candidates_a[0]), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=caption_a):

        resp_a2 = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "Item A1", "whatsapp_number": user_a, "active_mode": "reseller"}
        )
        assert resp_a2.status_code == 200

    # User A's selection consumed and draft created
    assert key_a not in PENDING_SELECTIONS
    assert key_a in PENDING_LISTINGS
    assert PENDING_LISTINGS[key_a]["matched_product_name"] == "Item A1"

    # User B's selection remains untouched
    assert key_b in PENDING_SELECTIONS
    assert key_b not in PENDING_LISTINGS
    assert PENDING_SELECTIONS[key_b]["options"][0]["name"] == "Item B1"


def test_api_cross_mode_session_isolation_same_phone(api_client):
    phone = "whatsapp:+917777777777"
    reseller_key = _pending_key(phone, "reseller")
    customer_key = _pending_key(phone, "customer")

    reseller_product = {
        "product_id": "P-RES", "name": "Reseller Kurti", "meesho_cost_inr": 200, "suggested_selling_price_inr": 350
    }
    customer_product = {
        "product_id": "P-CUST", "name": "Customer Saree", "suggested_selling_price_inr": 599, "base_image_url": "https://img.c"
    }

    mock_caption = CatalogCaptionResponse(
        ui_text="Reseller draft", tts_text="कैप्शन", product_name_tts="Reseller Kurti"
    )
    mock_cust_resp = CustomerAgentResponse(
        ui_text="Customer Saree info", tts_text="कस्टमर साड़ी", answered_from_product_context=True,
        return_retention_triggered=False, purchase_intent_detected=False, grounded_via_recent_item=False
    )

    # 1. Reseller Turn via API
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=reseller_product), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption):

        resp_res = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "Reseller Kurti", "whatsapp_number": phone, "active_mode": "reseller"}
        )
        assert resp_res.status_code == 200

    # 2. Customer Turn via API
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CUSTOMER")), \
         patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[customer_product]), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_cust_resp):

        resp_cust = api_client.post(
            "/api/v1/chat/send",
            data={"text_message": "Customer Saree", "whatsapp_number": phone, "active_mode": "customer"}
        )
        assert resp_cust.status_code == 200

    # Verify both stores remain completely isolated on the same phone
    assert reseller_key in PENDING_LISTINGS
    assert customer_key not in PENDING_LISTINGS

    assert customer_key in LAST_VIEWED_PRODUCT
    assert reseller_key not in LAST_VIEWED_PRODUCT
    assert LAST_VIEWED_PRODUCT[customer_key]["name"] == "Customer Saree"
    assert PENDING_LISTINGS[reseller_key]["matched_product_name"] == "Reseller Kurti"


def test_api_system_trigger_return_isolation(api_client):
    from backend.core.gemini_utils import ReturnsAgentResponse

    phone = "whatsapp:+919876543210"
    customer_key = _pending_key(phone, "customer")
    reseller_key = _pending_key(phone, "reseller")

    mock_resp = ReturnsAgentResponse(
        ui_text="Proactive outreach message",
        tts_text="आउटरीच",
        suggests_alternative=False
    )

    with patch("backend.core.agents.returns._lookup_product_by_name", return_value={"name": "Silk Saree"}), \
         patch("backend.core.agents.returns.generate_structured_with_fallback", return_value=mock_resp):
        resp = api_client.post(
            "/api/v1/system/trigger-return",
            data={"whatsapp_number": phone, "order_id": "ORD-555", "product_name": "Silk Saree"}
        )
        assert resp.status_code == 200

    # Seeds customer return state
    assert customer_key in PENDING_RETURNS
    assert PENDING_RETURNS[customer_key]["order_id"] == "ORD-555"

    # Reseller state store must remain unaffected
    assert reseller_key not in PENDING_RETURNS
    assert reseller_key not in PENDING_LISTINGS

