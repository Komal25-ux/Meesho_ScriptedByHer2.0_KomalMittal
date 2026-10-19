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
)


@pytest.fixture
def graph():
    return get_sakhi_agent_graph()


def test_multiturn_catalog_picker_to_draft(graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "reseller")

    candidates = [
        {"product_id": "K1", "name": "Blue Kurti", "suggested_selling_price_inr": 450, "meesho_cost_inr": 250},
        {"product_id": "K2", "name": "Red Kurti", "suggested_selling_price_inr": 480, "meesho_cost_inr": 270},
    ]

    # ── Turn 1: Reseller asks for kurtis ──
    state_t1 = make_state(raw_input="kurtis dikhao", whatsapp_number=phone, active_mode="reseller")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="kurtis"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates):

        res_t1 = graph.invoke(state_t1)
        assert res_t1["reply_product_options"] is not None
        assert session_key in PENDING_SELECTIONS
        assert session_key not in PENDING_LISTINGS

    # ── Turn 2: Reseller selects "Blue Kurti" ──
    mock_selected_product = candidates[0]
    mock_caption = CatalogCaptionResponse(
        ui_text="Blue Kurti Caption", tts_text="ब्लू कुर्ती", product_name_tts="ब्लू कुर्ती"
    )

    state_t2 = make_state(raw_input="Blue Kurti", whatsapp_number=phone, active_mode="reseller")
    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=mock_selected_product), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption):

        res_t2 = graph.invoke(state_t2)

        # Selection gate should have intercepted and routed to catalog_agent
        assert "Blue Kurti" in res_t2["reply_text"]
        assert session_key not in PENDING_SELECTIONS  # Consumed
        assert session_key in PENDING_LISTINGS        # Draft now created
        assert PENDING_LISTINGS[session_key]["matched_product_name"] == "Blue Kurti"


def test_multiturn_catalog_draft_price_negotiation_to_finalize(graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "reseller")

    # Initial state with existing draft
    PENDING_LISTINGS[session_key] = {
        "matched_product_name": "Silk Kurti",
        "selling_price": 500,
        "cost": 300,
        "base_image_url": "https://img.com/silk.jpg",
        "listing_payload": {
            "product_name": "Silk Kurti",
            "category": "kurtis",
            "selling_price_inr": 500,
            "cost_price_inr": 300,
            "whatsapp_caption": "Silk Kurti Caption",
            "image_url": "https://img.com/silk.jpg",
        },
        "matched_product": {
            "product_id": "P-SILK",
            "name": "Silk Kurti",
            "category": "kurtis",
            "base_image_url": "https://img.com/silk.jpg",
        }
    }

    # ── Turn 1: Reseller requests price modification to ₹650 ──
    mock_caption_650 = CatalogCaptionResponse(
        ui_text="New Silk Kurti Caption @ 650", tts_text="सिल्क कुर्ती 650", product_name_tts="सिल्क कुर्ती"
    )
    state_t1 = make_state(raw_input="price 650 kar do", whatsapp_number=phone, active_mode="reseller")

    with patch("backend.core.orchestrator.classify_approval_intent", return_value="modify"), \
         patch("backend.core.orchestrator.generate_whatsapp_caption", return_value=mock_caption_650):

        res_t1 = graph.invoke(state_t1)
        assert res_t1["reply_price"] == 650
        assert "price update kar diya" in res_t1["reply_text"]
        assert PENDING_LISTINGS[session_key]["selling_price"] == 650

    # ── Turn 2: Reseller approves the draft ──
    state_t2 = make_state(raw_input="haan post kar do", whatsapp_number=phone, active_mode="reseller")

    with patch("backend.core.orchestrator.classify_approval_intent", return_value="approve"):
        res_t2 = graph.invoke(state_t2)

        assert res_t2["listing_finalized"] is True
        assert res_t2["reply_price"] == 650
        assert "live post ho gaya hai" in res_t2["reply_text"]
        # Consumed and cleared
        assert session_key not in PENDING_LISTINGS


def test_multiturn_customer_context_lock_flow(graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    customer_key = _pending_key(phone, "customer")

    # Simulate listing finalization having armed the context lock
    FRESH_BROADCAST_LOCK[customer_key] = True
    LAST_VIEWED_PRODUCT[customer_key] = {
        "product_id": "SKU-JUST-POSTED",
        "name": "Floral Anarkali",
        "suggested_selling_price_inr": 899,
        "base_image_url": "https://img.com/anarkali.jpg",
    }

    mock_resp = CustomerAgentResponse(
        ui_text="Ji, Floral Anarkali abhi post hua hai - price ₹899 hai.",
        tts_text="जी, फ्लोरल अनारकली अभी पोस्ट हुआ है",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=True
    )

    # ── Turn 1: Customer's very first reply ("I want to buy") ──
    state_t1 = make_state(raw_input="I want to buy", whatsapp_number=phone, active_mode="customer")

    with patch("backend.core.orchestrator.classify_buying_interest", return_value=True), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp):

        res_t1 = graph.invoke(state_t1)
        assert "Floral Anarkali" in res_t1["reply_text"]
        assert res_t1["reply_image_url"] == "https://img.com/anarkali.jpg"
        # Lock is popped (one-shot)
        assert customer_key not in FRESH_BROADCAST_LOCK
        # But item stays grounded in LAST_VIEWED_PRODUCT
        assert LAST_VIEWED_PRODUCT[customer_key]["name"] == "Floral Anarkali"

    # ── Turn 2: Next turn disarmed from lock, uses regular follow-up ──
    state_t2 = make_state(raw_input="colors kya hain?", whatsapp_number=phone, active_mode="customer")

    mock_followup_resp = CustomerAgentResponse(
        ui_text="Isme Pink aur Yellow colors hain.",
        tts_text="इसमें पिंक और येलो हैं",
        answered_from_product_context=True,
        return_retention_triggered=False,
        purchase_intent_detected=False,
        grounded_via_recent_item=True
    )

    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CUSTOMER")), \
         patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.classify_attribute_followup", return_value=True), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=mock_followup_resp):

        res_t2 = graph.invoke(state_t2)
        assert "Isme Pink aur Yellow colors hain." in res_t2["reply_text"]


def test_multiturn_returns_retention_funnel(graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+919876543210"
    customer_key = _pending_key(phone, "customer")

    # Seeded by proactive outreach
    PENDING_RETURNS[customer_key] = {
        "order_id": "ORD-777",
        "product_name": "Designer Saree",
        "stage": "awaiting_grievance",
        "original_product": {"name": "Designer Saree", "colors": ["Red", "Green"]},
    }

    # ── Turn 1: Grievance reported ("color pasand nahi aaya") ──
    mock_resp_t1 = ReturnsAgentResponse(
        ui_text="Maaf kijiyega! Isme Green color bhi available hai, kya exchange karwayein?",
        tts_text="माफ़ कीजियेगा! इसमें ग्रीन कलर भी है",
        suggests_alternative=True
    )

    state_t1 = make_state(raw_input="color pasand nahi aaya", whatsapp_number=phone, active_mode="customer")

    with patch("backend.core.orchestrator.classify_return_grievance", return_value="color_style_issue"), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp_t1):

        res_t1 = graph.invoke(state_t1)
        assert "Green color" in res_t1["reply_text"]
        assert PENDING_RETURNS[customer_key]["stage"] == "awaiting_confirmation"
        assert PENDING_RETURNS[customer_key]["grievance"] == "color_style_issue"

    # ── Turn 2: Customer accepts exchange ("theek hai green bhej do") ──
    mock_resp_t2 = ReturnsAgentResponse(
        ui_text="Ji bilkul, Green color Saree ka exchange request initiate kar diya hai!",
        tts_text="जी बिल्कुल",
        suggests_alternative=False
    )

    state_t2 = make_state(raw_input="theek hai green bhej do", whatsapp_number=phone, active_mode="customer")

    with patch("backend.core.orchestrator.classify_exchange_confirmation", return_value="accept"), \
         patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=mock_resp_t2):

        res_t2 = graph.invoke(state_t2)
        assert "exchange request initiate kar diya hai" in res_t2["reply_text"]
        assert res_t2["reply_handoff_triggered"] is True
        # Terminal: popped from PENDING_RETURNS
        assert customer_key not in PENDING_RETURNS


def test_multiturn_multi_user_isolation(graph, make_state, mock_db_orchestrator):
    user_a = "whatsapp:+911111111111"
    user_b = "whatsapp:+912222222222"
    key_a = _pending_key(user_a, "reseller")
    key_b = _pending_key(user_b, "reseller")

    candidates_a = [{"product_id": "A1", "name": "Item A1", "suggested_selling_price_inr": 300, "meesho_cost_inr": 200}]
    candidates_b = [{"product_id": "B1", "name": "Item B1", "suggested_selling_price_inr": 600, "meesho_cost_inr": 400}]

    # User A Turn 1:
    state_a = make_state(raw_input="Item A", whatsapp_number=user_a, active_mode="reseller")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="sarees"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates_a):
        graph.invoke(state_a)

    # User B Turn 1:
    state_b = make_state(raw_input="Item B", whatsapp_number=user_b, active_mode="reseller")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="kurtis"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates_b):
        graph.invoke(state_b)

    assert key_a in PENDING_SELECTIONS
    assert key_b in PENDING_SELECTIONS
    assert PENDING_SELECTIONS[key_a]["options"][0]["name"] == "Item A1"
    assert PENDING_SELECTIONS[key_b]["options"][0]["name"] == "Item B1"

    # User A selects Item A1
    caption_a = CatalogCaptionResponse(ui_text="Draft A1", tts_text="ड्राफ्ट A1", product_name_tts="Item A1")
    state_a2 = make_state(raw_input="Item A1", whatsapp_number=user_a, active_mode="reseller")
    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=candidates_a[0]), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=caption_a):
        graph.invoke(state_a2)

    # User A selection resolved, User B selection STILL intact
    assert key_a not in PENDING_SELECTIONS
    assert key_a in PENDING_LISTINGS
    assert key_b in PENDING_SELECTIONS
    assert key_b not in PENDING_LISTINGS


def test_multiturn_cross_mode_isolation_same_phone(graph, make_state, mock_db_orchestrator):
    phone = "whatsapp:+918888888888"
    reseller_key = _pending_key(phone, "reseller")
    customer_key = _pending_key(phone, "customer")

    product_reseller = {"product_id": "P-R", "name": "Reseller Product", "meesho_cost_inr": 200, "suggested_selling_price_inr": 350}
    product_customer = {"product_id": "P-C", "name": "Customer Product", "suggested_selling_price_inr": 500, "base_image_url": "https://c.jpg"}

    caption = CatalogCaptionResponse(ui_text="Reseller caption", tts_text="कैप्शन", product_name_tts="Reseller Product")
    cust_resp = CustomerAgentResponse(
        ui_text="Customer info", tts_text="कस्टमर जानकारी", answered_from_product_context=True,
        return_retention_triggered=False, purchase_intent_detected=False, grounded_via_recent_item=False
    )

    # ── Turn 1 (Reseller Mode): Creates Draft ──
    state_t1 = make_state(raw_input="Reseller Product", whatsapp_number=phone, active_mode="reseller")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CATALOG")), \
         patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=product_reseller), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=caption):
        graph.invoke(state_t1)

    assert reseller_key in PENDING_LISTINGS
    assert customer_key not in PENDING_LISTINGS

    # ── Turn 2 (Customer Mode): Browses Product ──
    state_t2 = make_state(raw_input="Customer Product", whatsapp_number=phone, active_mode="customer")
    with patch("backend.core.orchestrator.generate_structured_with_fallback", return_value=IntentRouter(route_to="CUSTOMER")), \
         patch("backend.core.agents.customer.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.customer.extract_category_intent", return_value=None), \
         patch("backend.core.agents.customer.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.customer.db_client.match_products", return_value=[product_customer]), \
         patch("backend.core.agents.customer.generate_structured_with_fallback", return_value=cust_resp):
        graph.invoke(state_t2)

    assert customer_key in LAST_VIEWED_PRODUCT
    assert reseller_key not in LAST_VIEWED_PRODUCT
    # Reseller draft was untouched by the customer turn
    assert reseller_key in PENDING_LISTINGS
