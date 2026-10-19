import pytest
from unittest.mock import patch, MagicMock

from backend.core.agents.customer import run_customer_agent, _answer_established_item_followup
from backend.core.session import (
    LAST_VIEWED_PRODUCT,
    PENDING_SELECTIONS,
    PENDING_RETURNS,
    LAST_REQUESTED_CATEGORY,
    SHOWN_PRODUCT_IDS,
)
from backend.core.state import _pending_key
from backend.core.gemini_utils import CustomerAgentResponse
from backend.core.constants import (
    CUSTOMER_ZERO_HALLUCINATION_REFUSAL,
    CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS,
    DRILL_DOWN_CTA,
    DRILL_DOWN_CTA_TTS,
)


@pytest.fixture
def sample_product():
    return {
        "product_id": "SKU-909",
        "name": "Pink Georgette Saree",
        "category": "sarees",
        "meesho_cost_inr": 400,
        "suggested_selling_price_inr": 650,
        "sizes": ["Free Size"],
        "colors": ["Pink", "Magenta"],
        "base_image_url": "https://example.com/pink_saree.jpg",
        "description": "Georgette saree with lace border"
    }


def test_customer_agent_single_grounded_product_query(make_state, sample_product):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="Pink saree ke details batao", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text="Pink Georgette Saree ₹650 mein available hai. Iska material georgette hai.",
        tts_text="पिंक जॉर्जेट साड़ी 650 रुपये में उपलब्ध है।",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=False
    )

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value="sarees"), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[sample_product]), \
         patch("backend.core.agents.customer.db_client.is_product_listed", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = run_customer_agent(state)

        assert res_state["reply_text"] == mock_resp.ui_text
        assert res_state["reply_image_url"] == sample_product["base_image_url"]

        session_key = _pending_key(phone, "customer")
        assert session_key in LAST_VIEWED_PRODUCT
        assert LAST_VIEWED_PRODUCT[session_key]["product_id"] == "SKU-909"


def test_customer_agent_zero_hallucination_refusal(make_state):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="kya isme leather straps hain?", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text=CUSTOMER_ZERO_HALLUCINATION_REFUSAL,
        tts_text=CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS,
        answered_from_product_context=False,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=False
    )

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[]), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = run_customer_agent(state)

        assert res_state["reply_text"] == CUSTOMER_ZERO_HALLUCINATION_REFUSAL
        assert res_state["reply_image_url"] is None


def test_customer_agent_purchase_confirmation_intent(make_state, sample_product):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "customer")
    LAST_VIEWED_PRODUCT[session_key] = sample_product

    state = make_state(
        raw_input="isko order kar do",
        whatsapp_number=phone,
        active_mode="customer",
        reseller_id="reseller-123"
    )

    mock_resp = CustomerAgentResponse(
        ui_text="Ji zaroor! Aapka order confirm karne ke liye main reseller ko notify kar rahi hoon. Sunita Didi jald hi aapse sampark karengi. 🛍️",
        tts_text="जी ज़रूर! आपका ऑर्डर कन्फर्म करने के लिए मैं रीसेलर को नोटिफाई कर रही हूँ.",
        answered_from_product_context=False,
        return_retention_triggered=False,
        purchase_intent_detected=True,
        grounded_via_recent_item=False
    )

    saved_order_mock = {
        "id": "ORD-555",
        "product_name": "Pink Georgette Saree",
        "unit_price_inr": 650,
        "listing_id": "LISTING-1"
    }

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.classify_attribute_followup", return_value=False), \
         patch("backend.core.agents.customer.db_client.is_product_listed", return_value=True), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[]), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.db_client.get_listing_id", return_value="LISTING-1"), \
         patch("backend.core.agents.customer.db_client.save_order", return_value=saved_order_mock) as mock_save_order, \
         patch("backend.core.agents.customer.db_client.log_agent_event") as mock_log:

        res_state = run_customer_agent(state)

        assert res_state["reply_purchase_intent_detected"] is True
        assert res_state["reply_order_id"] == "ORD-555"
        assert res_state["reply_confirmed_product_name"] == "Pink Georgette Saree"
        assert res_state["reply_confirmed_product_price"] == 650
        assert res_state["reply_image_url"] is None

        # Verify save_order payload
        mock_save_order.assert_called_once()
        order_arg = mock_save_order.call_args[0][0]
        assert order_arg["reseller_id"] == "reseller-123"
        assert order_arg["buyer_whatsapp"] == phone
        assert order_arg["product_id"] == "SKU-909"
        assert order_arg["total_amount_inr"] == 650

        # LAST_VIEWED_PRODUCT should be popped after purchase
        assert session_key not in LAST_VIEWED_PRODUCT

        mock_log.assert_called_once()
        assert mock_log.call_args[0][0]["event_type"] == "customer_purchase_intent"


def test_customer_agent_return_retention_hook(make_state, sample_product):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="ye saree return karni hai", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text="Oh! Maaf kijiyega ki product aapki ummeedon par khara nahi utra. Kya main jaan sakti hu ki issue kya hai? Size, color ya fitting mein koi dikkat aayi? Main turant isko exchange karwa sakti hu. 🔄",
        tts_text="ओह! माफ़ कीजियेगा की प्रोडक्ट आपकी उम्मीदों पर खरा नहीं उतरा.",
        answered_from_product_context=False,
        return_retention_triggered=True,
        purchase_intent_detected=False,
        grounded_via_recent_item=False
    )

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[sample_product]), \
         patch("backend.core.agents.customer.db_client.is_product_listed", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = run_customer_agent(state)

        session_key = _pending_key(phone, "customer")
        assert session_key in PENDING_RETURNS
        pending_return = PENDING_RETURNS[session_key]
        assert pending_return["stage"] == "awaiting_grievance"
        assert pending_return["product_name"] == "Pink Georgette Saree"


def test_customer_agent_ambiguous_browse_shows_picker(make_state):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="saree dikhao", whatsapp_number=phone, active_mode="customer")

    candidates = [
        {"product_id": f"S-{i}", "name": f"Saree {i}", "suggested_selling_price_inr": 500 + i * 50}
        for i in range(1, 4)
    ]

    mock_resp = CustomerAgentResponse(
        ui_text="Aapke liye options:",
        tts_text="आपके लिए ऑप्शंस:",
        answered_from_product_context=False,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=False
    )

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value="sarees"), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=candidates), \
         patch("backend.core.agents.customer.db_client.is_product_listed", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.db_client.log_agent_event") as mock_log:

        res_state = run_customer_agent(state)

        assert "kuch milte-julte options mile hain" in res_state["reply_text"]
        assert res_state["reply_product_options"] is not None
        assert len(res_state["reply_product_options"]) == 3
        assert res_state["reply_image_url"] is None

        session_key = _pending_key(phone, "customer")
        assert session_key in PENDING_SELECTIONS
        assert PENDING_SELECTIONS[session_key]["agent"] == "customer"

        mock_log.assert_called_once()
        assert mock_log.call_args[0][0]["event_type"] == "customer_selection_prompt"


def test_customer_agent_category_exhaustion(make_state):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "customer")
    LAST_REQUESTED_CATEGORY[session_key] = "kurtis"
    SHOWN_PRODUCT_IDS[session_key] = ["K-1", "K-2"]

    state = make_state(raw_input="aur kurtis dikhao", whatsapp_number=phone, active_mode="customer")

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value="kurtis"), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[]), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = run_customer_agent(state)

        assert "is category mein bas itne hi options uplabdh hain" in res_state["reply_text"]
        assert res_state["reply_product_options"] is None


def test_customer_agent_deterministic_drill_down_short_circuit(make_state, sample_product):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "customer")
    LAST_VIEWED_PRODUCT[session_key] = sample_product

    state = make_state(raw_input="iska fabric kya hai", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text="Yeh pure georgette fabric mein hai.",
        tts_text="यह प्योर जॉर्जेट फैब्रिक में है।",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=True
    )

    with patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.classify_attribute_followup", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.embed_content_with_fallback") as mock_embed, \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = run_customer_agent(state)

        # Vector search should be completely bypassed
        mock_embed.assert_not_called()

        # Follow-up must enforce CTA and suppress image
        assert DRILL_DOWN_CTA in res_state["reply_text"]
        assert DRILL_DOWN_CTA_TTS in res_state["reply_tts_text"]
        assert res_state["reply_image_url"] is None
        assert LAST_VIEWED_PRODUCT[session_key] == sample_product


def test_answer_established_item_followup_llm_success(make_state, sample_product):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "customer")
    state = make_state(raw_input="colors kya hain?", whatsapp_number=phone)

    mock_resp = CustomerAgentResponse(
        ui_text="Isme Pink aur Magenta colors available hain.",
        tts_text="इसमें पिंक और मजेंटा कलर्स उपलब्ध हैं।",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=True
    )

    with patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = _answer_established_item_followup(
            state, sample_product, "colors kya hain?", session_key, phone, 0.0
        )

        assert "Isme Pink aur Magenta colors available hain." in res_state["reply_text"]
        assert DRILL_DOWN_CTA in res_state["reply_text"]
        assert DRILL_DOWN_CTA_TTS in res_state["reply_tts_text"]
        assert res_state["reply_image_url"] is None
        assert res_state["reply_product_options"] is None
        assert LAST_VIEWED_PRODUCT[session_key] == sample_product


def test_answer_established_item_followup_llm_fallback(make_state, sample_product):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "customer")
    state = make_state(raw_input="size kya hai?", whatsapp_number=phone)

    with patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=None), \
         patch("backend.core.agents.customer.db_client.log_agent_event"):

        res_state = _answer_established_item_followup(
            state, sample_product, "size kya hai?", session_key, phone, 0.0
        )

        assert "Iske available sizes hain: Free Size." in res_state["reply_text"]
        assert DRILL_DOWN_CTA in res_state["reply_text"]
        assert DRILL_DOWN_CTA_TTS in res_state["reply_tts_text"]
        assert res_state["reply_image_url"] is None
