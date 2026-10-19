import pytest
from unittest.mock import patch

from backend.core.agents.catalog import run_catalog_agent
from backend.core.agents.customer import run_customer_agent
from backend.core.agents.returns import run_returns_proactive_outreach
from backend.core.session import (
    PENDING_LISTINGS,
    PENDING_SELECTIONS,
    LAST_VIEWED_PRODUCT,
    PENDING_RETURNS,
)
from backend.core.state import _pending_key
from backend.core.gemini_utils import CatalogCaptionResponse, CustomerAgentResponse


def test_cross_user_catalog_agent_isolation(make_state):
    user_a = "whatsapp:+911111111111"
    user_b = "whatsapp:+912222222222"

    options_a = [
        {"product_id": "P-A1", "name": "Item A1", "meesho_cost_inr": 200, "suggested_selling_price_inr": 350},
        {"product_id": "P-A2", "name": "Item A2", "meesho_cost_inr": 220, "suggested_selling_price_inr": 380},
    ]
    options_b = [
        {"product_id": "P-B1", "name": "Item B1", "meesho_cost_inr": 500, "suggested_selling_price_inr": 750},
        {"product_id": "P-B2", "name": "Item B2", "meesho_cost_inr": 520, "suggested_selling_price_inr": 780},
    ]

    state_a = make_state(raw_input="saree dikhao", whatsapp_number=user_a, active_mode="reseller")
    state_b = make_state(raw_input="kurti dikhao", whatsapp_number=user_b, active_mode="reseller")

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", side_effect=["sarees", "kurtis"]), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", side_effect=[options_a, options_b]), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):

        run_catalog_agent(state_a)
        run_catalog_agent(state_b)

        key_a = _pending_key(user_a, "reseller")
        key_b = _pending_key(user_b, "reseller")

        assert key_a != key_b
        assert key_a in PENDING_SELECTIONS
        assert key_b in PENDING_SELECTIONS

        assert PENDING_SELECTIONS[key_a]["options"][0]["name"] == "Item A1"
        assert PENDING_SELECTIONS[key_b]["options"][0]["name"] == "Item B1"


def test_cross_user_customer_agent_isolation(make_state):
    user_a = "whatsapp:+911111111111"
    user_b = "whatsapp:+912222222222"

    product_a = {"product_id": "SKU-A", "name": "Product A", "suggested_selling_price_inr": 499, "base_image_url": "https://img.a"}
    product_b = {"product_id": "SKU-B", "name": "Product B", "suggested_selling_price_inr": 899, "base_image_url": "https://img.b"}

    state_a = make_state(raw_input="Product A", whatsapp_number=user_a, active_mode="customer")
    state_b = make_state(raw_input="Product B", whatsapp_number=user_b, active_mode="customer")

    mock_resp_a = CustomerAgentResponse(
        ui_text="Product A info", tts_text="Product A info", answered_from_product_context=True,
        return_retention_triggered=False, purchase_intent_detected=False, grounded_via_recent_item=False
    )
    mock_resp_b = CustomerAgentResponse(
        ui_text="Product B info", tts_text="Product B info", answered_from_product_context=True,
        return_retention_triggered=False, purchase_intent_detected=False, grounded_via_recent_item=False
    )

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", side_effect=[[product_a], [product_b]]), \
         patch("backend.core.agents.customer.db_client.is_product_listed", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", side_effect=[mock_resp_a, mock_resp_b]), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        run_customer_agent(state_a)
        run_customer_agent(state_b)

        key_a = _pending_key(user_a, "customer")
        key_b = _pending_key(user_b, "customer")

        assert key_a != key_b
        assert LAST_VIEWED_PRODUCT[key_a]["name"] == "Product A"
        assert LAST_VIEWED_PRODUCT[key_b]["name"] == "Product B"


def test_cross_mode_session_isolation_same_phone(make_state):
    phone = "whatsapp:+919999999999"

    product_reseller = {"product_id": "P-RES", "name": "Reseller Item", "meesho_cost_inr": 200, "suggested_selling_price_inr": 350}
    product_customer = {"product_id": "P-CUST", "name": "Customer Item", "suggested_selling_price_inr": 500, "base_image_url": "https://img.c"}

    mock_caption = CatalogCaptionResponse(
        ui_text="caption", tts_text="caption tts", product_name_tts="Reseller Item"
    )
    mock_cust_resp = CustomerAgentResponse(
        ui_text="Customer Item info", tts_text="Customer Item info", answered_from_product_context=True,
        return_retention_triggered=False, purchase_intent_detected=False, grounded_via_recent_item=False
    )

    # 1. Reseller mode action: Catalog draft
    state_res = make_state(raw_input="Reseller Item", whatsapp_number=phone, active_mode="reseller")
    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=product_reseller), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):
        run_catalog_agent(state_res)

    # 2. Customer mode action: Customer view
    state_cust = make_state(raw_input="Customer Item", whatsapp_number=phone, active_mode="customer")
    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[product_customer]), \
         patch("backend.core.agents.customer.db_client.is_product_listed", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_cust_resp), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):
        run_customer_agent(state_cust)

    reseller_key = _pending_key(phone, "reseller")
    customer_key = _pending_key(phone, "customer")

    assert reseller_key != customer_key
    assert reseller_key in PENDING_LISTINGS
    assert customer_key not in PENDING_LISTINGS
    assert customer_key in LAST_VIEWED_PRODUCT
    assert reseller_key not in LAST_VIEWED_PRODUCT
