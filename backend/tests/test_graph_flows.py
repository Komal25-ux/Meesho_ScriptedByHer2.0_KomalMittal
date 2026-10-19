import pytest
from unittest.mock import patch, MagicMock

from backend.core.orchestrator import get_sakhi_agent_graph
from backend.core.session import (
    PENDING_LISTINGS,
    PENDING_SELECTIONS,
    LAST_VIEWED_PRODUCT,
    FRESH_BROADCAST_LOCK,
    PENDING_RETURNS,
)
from backend.core.state import _pending_key
from backend.core.gemini_utils import (
    IntentRouter,
    CatalogCaptionResponse,
    CustomerAgentResponse,
    ReturnsAgentResponse,
    AgentResponse,
)
from backend.core.constants import DRILL_DOWN_CTA


@pytest.fixture
def compiled_graph():
    return get_sakhi_agent_graph()


def test_graph_flow_simple_catalog_search(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="Cotton Saree", whatsapp_number=phone, active_mode="reseller")

    mock_product = {
        "product_id": "SKU-C1",
        "name": "Cotton Saree",
        "meesho_cost_inr": 300,
        "suggested_selling_price_inr": 499,
        "base_image_url": "https://img.com/cotton.jpg",
    }
    mock_caption = CatalogCaptionResponse(
        ui_text="Cotton Saree caption", tts_text="कॉटन साड़ी", product_name_tts="कॉटन साड़ी"
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=mock_product), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption):

        final_state = compiled_graph.invoke(state)

        assert final_state["detected_intent"] == "CATALOG"
        assert "Cotton Saree" in final_state["reply_text"]
        assert final_state["reply_image_url"] == "https://img.com/cotton.jpg"
        assert final_state["reply_price"] == 499

        session_key = _pending_key(phone, "reseller")
        assert session_key in PENDING_LISTINGS
        assert PENDING_LISTINGS[session_key]["selling_price"] == 499


def test_graph_flow_ambiguous_catalog_selection(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="kurtis dikhao", whatsapp_number=phone, active_mode="reseller")

    candidates = [
        {"product_id": "K1", "name": "Kurti 1", "suggested_selling_price_inr": 399, "meesho_cost_inr": 200},
        {"product_id": "K2", "name": "Kurti 2", "suggested_selling_price_inr": 499, "meesho_cost_inr": 250},
    ]

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="kurtis"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates):

        final_state = compiled_graph.invoke(state)

        assert final_state["reply_product_options"] is not None
        assert len(final_state["reply_product_options"]) == 2
        session_key = _pending_key(phone, "reseller")
        assert session_key in PENDING_SELECTIONS
        assert session_key not in PENDING_LISTINGS


def test_graph_flow_listing_approval_and_finalization(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "reseller")

    PENDING_LISTINGS[session_key] = {
        "matched_product_name": "Banarasi Saree",
        "selling_price": 799,
        "cost": 450,
        "base_image_url": "https://img.com/banarasi.jpg",
        "listing_payload": {
            "product_name": "Banarasi Saree",
            "category": "sarees",
            "selling_price_inr": 799,
            "cost_price_inr": 450,
            "whatsapp_caption": "Banarasi Saree Live Caption",
            "image_url": "https://img.com/banarasi.jpg",
        },
        "matched_product": {
            "product_id": "P-BANARASI",
            "name": "Banarasi Saree",
            "category": "sarees",
            "base_image_url": "https://img.com/banarasi.jpg",
        }
    }

    state = make_state(raw_input="haan post kar do", whatsapp_number=phone, active_mode="reseller")

    with patch("backend.core.orchestrator.classify_approval_intent", return_value="approve"):
        final_state = compiled_graph.invoke(state)

        assert final_state["listing_finalized"] is True
        assert final_state["listing_product_name"] == "Banarasi Saree"
        assert "live post ho gaya hai" in final_state["reply_text"]
        assert final_state["reply_price"] == 799

        # Pending listing should be cleared
        assert session_key not in PENDING_LISTINGS

        # Customer session context lock should be armed
        customer_key = _pending_key(phone, "customer")
        assert FRESH_BROADCAST_LOCK.get(customer_key) is True
        assert LAST_VIEWED_PRODUCT.get(customer_key)["name"] == "Banarasi Saree"


def test_graph_flow_customer_product_question(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="Red Saree details", whatsapp_number=phone, active_mode="customer")

    product = {
        "product_id": "SKU-RED",
        "name": "Red Saree",
        "category": "sarees",
        "suggested_selling_price_inr": 599,
        "base_image_url": "https://img.com/red.jpg",
    }
    mock_cust_resp = CustomerAgentResponse(
        ui_text="Red Saree ₹599 mein available hai.",
        tts_text="रेड साड़ी 599 रुपये में उपलब्ध है।",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=False
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CUSTOMER")), \
         patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value="sarees"), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[product]), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_cust_resp):

        final_state = compiled_graph.invoke(state)

        assert "Red Saree ₹599 mein available hai" in final_state["reply_text"]
        assert final_state["reply_image_url"] == "https://img.com/red.jpg"
        customer_key = _pending_key(phone, "customer")
        assert LAST_VIEWED_PRODUCT[customer_key]["name"] == "Red Saree"


def test_graph_flow_customer_followup_drill_down(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    customer_key = _pending_key(phone, "customer")

    LAST_VIEWED_PRODUCT[customer_key] = {
        "product_id": "SKU-RED",
        "name": "Red Saree",
        "category": "sarees",
        "sizes": ["Free Size"],
        "suggested_selling_price_inr": 599,
        "base_image_url": "https://img.com/red.jpg",
    }

    state = make_state(raw_input="size kya hai?", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text="Yeh Free Size mein available hai.",
        tts_text="यह फ्री साइज में उपलब्ध है।",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=True
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CUSTOMER")), \
         patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.classify_attribute_followup", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp):

        final_state = compiled_graph.invoke(state)

        assert "Yeh Free Size mein available hai." in final_state["reply_text"]
        assert DRILL_DOWN_CTA in final_state["reply_text"]
        # Media suppressed for drill-down follow-up
        assert final_state["reply_image_url"] is None


def test_graph_flow_customer_purchase_confirmation(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    customer_key = _pending_key(phone, "customer")

    LAST_VIEWED_PRODUCT[customer_key] = {
        "product_id": "SKU-RED",
        "name": "Red Saree",
        "category": "sarees",
        "suggested_selling_price_inr": 599,
    }

    state = make_state(raw_input="isko order kar do", whatsapp_number=phone, active_mode="customer")

    mock_resp = CustomerAgentResponse(
        ui_text="Ji zaroor! Aapka order confirm karne ke liye main reseller ko notify kar rahi hoon.",
        tts_text="जी ज़रूर! आपका ऑर्डर कन्फर्म करने के लिए मैं रीसेलर को नोटिफाई कर रही हूँ.",
        answered_from_product_context=False,
        return_retention_triggered=False,
        purchase_intent_detected=True,
        grounded_via_recent_item=False
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CUSTOMER")), \
         patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.classify_attribute_followup", return_value=False), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[]), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_resp):

        final_state = compiled_graph.invoke(state)

        assert final_state["reply_purchase_intent_detected"] is True
        assert final_state["reply_confirmed_product_name"] == "Red Saree"
        assert customer_key not in LAST_VIEWED_PRODUCT


def test_graph_flow_pending_return_intercept(compiled_graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    customer_key = _pending_key(phone, "customer")

    PENDING_RETURNS[customer_key] = {
        "order_id": "ORD-123",
        "product_name": "Kurti",
        "stage": "awaiting_grievance",
        "original_product": {"name": "Kurti", "sizes": ["M", "L"]},
    }

    state = make_state(raw_input="size tight hai", whatsapp_number=phone, active_mode="customer")

    mock_resp = ReturnsAgentResponse(
        ui_text="Maaf kijiyega didi, kya aapko L size exchange karwa du?",
        tts_text="माफ़ कीजियेगा दीदी",
        suggests_alternative=True
    )

    with patch("backend.core.orchestrator.classify_return_grievance", return_value="size_issue"), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp):

        final_state = compiled_graph.invoke(state)

        assert "Maaf kijiyega didi, kya aapko L size exchange karwa du?" in final_state["reply_text"]
        assert customer_key in PENDING_RETURNS
        assert PENDING_RETURNS[customer_key]["stage"] == "awaiting_confirmation"


def test_graph_flow_growth_coaching(compiled_graph, make_state, mock_db_orchestrator):
    state = make_state(raw_input="weekly sales report", active_mode="reseller")

    mock_growth_resp = AgentResponse(
        ui_text="Namaste Sunita Didi! Aapka pichle hafte ka profit ₹2,500 raha.",
        tts_text="नमस्ते सुनीता दीदी! आपका पिछले हफ्ते का प्रॉफिट दो हज़ार पाँच सौ रुपये रहा।"
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="GROWTH")), \
         patch("backend.core.agents.growth.generate_structured_with_fallback", return_value=mock_growth_resp):

        final_state = compiled_graph.invoke(state)

        assert final_state["detected_intent"] == "GROWTH"
        assert "Aapka pichle hafte ka profit ₹2,500 raha" in final_state["reply_text"]


def test_graph_flow_general_handler(compiled_graph, make_state, mock_db_orchestrator):
    state = make_state(raw_input="namaste didi", active_mode="reseller")

    mock_resp = AgentResponse(
        ui_text="Namaste Sunita Didi! Main aapki business Sakhi hu.",
        tts_text="नमस्ते सुनीता दीदी! मैं आपकी बिज़नेस सखी हूँ।"
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="GENERAL")), \
         patch("backend.core.agents.general.generate_structured_with_fallback", return_value=mock_resp):

        final_state = compiled_graph.invoke(state)

        assert final_state["detected_intent"] == "GENERAL"
        assert "Main aapki business Sakhi hu" in final_state["reply_text"]


def test_graph_flow_outage_fallback_reaches_general_safely(compiled_graph, make_state, mock_db_orchestrator):
    # When intent detection fails (e.g. LLM quota exhaustion), detect_intent defaults to GENERAL
    state = make_state(raw_input="anything during outage", active_mode="reseller")

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=None), \
         patch("backend.core.agents.general.generate_structured_with_fallback", return_value=None):

        final_state = compiled_graph.invoke(state)

        assert final_state["detected_intent"] == "GENERAL"
        assert "Main aapki business Sakhi hu" in final_state["reply_text"]
