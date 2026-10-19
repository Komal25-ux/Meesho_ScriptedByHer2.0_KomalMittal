import pytest
from unittest.mock import patch

from backend.core.agents.returns import run_returns_proactive_outreach
from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key
from backend.core.gemini_utils import ReturnsAgentResponse


def test_returns_proactive_outreach_llm_success():
    phone = "whatsapp:+919876543210"
    order_id = "ORD-999"
    product_name = "Red Banarasi Saree"
    reseller_name = "Sunita Didi"

    mock_product = {"product_id": "SKU-001", "name": product_name, "category": "sarees"}
    mock_resp = ReturnsAgentResponse(
        ui_text="Namaste! Order ORD-999 ke baare me poochhna tha. Kya size ya color issue hai?",
        tts_text="नमस्ते! आर्डर ORD-999 के बारे में पूछना था। क्या साइज या कलर इशू है?",
        suggests_alternative=False
    )

    with patch("backend.core.agents.returns._lookup_product_by_name", return_value=mock_product) as mock_lookup, \
         patch("backend.core.agents.returns.generate_structured_with_fallback", return_value=mock_resp) as mock_llm:

        result = run_returns_proactive_outreach(phone, order_id, product_name, reseller_name)

        assert result["reply_text"] == mock_resp.ui_text
        assert result["reply_tts_text"] == mock_resp.tts_text
        assert result["reply_image_url"] is None

        mock_lookup.assert_called_once_with(product_name)
        mock_llm.assert_called_once()

        # Verify session state mutation
        expected_key = _pending_key(phone, "customer")
        assert expected_key in PENDING_RETURNS
        pending_data = PENDING_RETURNS[expected_key]
        assert pending_data["order_id"] == order_id
        assert pending_data["product_name"] == product_name
        assert pending_data["reseller_name"] == reseller_name
        assert pending_data["original_product"] == mock_product
        assert pending_data["stage"] == "awaiting_grievance"


def test_returns_proactive_outreach_llm_fallback():
    phone = "whatsapp:+919876543210"
    order_id = "ORD-123"
    product_name = "Blue Kurti"

    with patch("backend.core.agents.returns._lookup_product_by_name", return_value={"name": "Blue Kurti"}), \
         patch("backend.core.agents.returns.generate_structured_with_fallback", return_value=None):

        result = run_returns_proactive_outreach(phone, order_id, product_name)

        assert "Blue Kurti return ki hai" in result["reply_text"]
        assert "Main ise exchange karwa sakti hu" in result["reply_text"]
        assert "ब्लू कुर्ती" in result["reply_tts_text"] or "Blue Kurti" in result["reply_tts_text"]
        assert result["reply_image_url"] is None

        expected_key = _pending_key(phone, "customer")
        assert expected_key in PENDING_RETURNS
        assert PENDING_RETURNS[expected_key]["order_id"] == order_id


def test_returns_proactive_outreach_lookup_none():
    phone = "whatsapp:+919876543210"

    with patch("backend.core.agents.returns._lookup_product_by_name", return_value=None), \
         patch("backend.core.agents.returns.generate_structured_with_fallback", return_value=None):

        result = run_returns_proactive_outreach(phone, "ORD-404", "Unknown Item")

        expected_key = _pending_key(phone, "customer")
        assert PENDING_RETURNS[expected_key]["original_product"] is None
        assert "Unknown Item return ki hai" in result["reply_text"]


def test_returns_proactive_outreach_user_isolation():
    user1 = "whatsapp:+911111111111"
    user2 = "whatsapp:+912222222222"

    with patch("backend.core.agents.returns._lookup_product_by_name", return_value=None), \
         patch("backend.core.agents.returns.generate_structured_with_fallback", return_value=None):

        run_returns_proactive_outreach(user1, "ORD-1", "Product 1")
        run_returns_proactive_outreach(user2, "ORD-2", "Product 2")

        key1 = _pending_key(user1, "customer")
        key2 = _pending_key(user2, "customer")

        assert key1 != key2
        assert PENDING_RETURNS[key1]["order_id"] == "ORD-1"
        assert PENDING_RETURNS[key2]["order_id"] == "ORD-2"
        assert PENDING_RETURNS[key1]["product_name"] == "Product 1"
        assert PENDING_RETURNS[key2]["product_name"] == "Product 2"
