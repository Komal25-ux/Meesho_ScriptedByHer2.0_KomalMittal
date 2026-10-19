import pytest
from unittest.mock import patch, MagicMock

from backend.core.agents.catalog import run_catalog_agent
from backend.core.session import PENDING_LISTINGS, PENDING_SELECTIONS, LAST_REQUESTED_CATEGORY, SHOWN_PRODUCT_IDS
from backend.core.state import _pending_key
from backend.core.gemini_utils import CatalogCaptionResponse


@pytest.fixture
def mock_caption():
    return CatalogCaptionResponse(
        ui_text="✨ *Silk Saree* ✨\nPrice: ₹599\nOrder now on WhatsApp!",
        tts_text="सिल्क साड़ी, कीमत 599 रुपये",
        product_name_tts="सिल्क साड़ी"
    )


def test_catalog_agent_share_trigger_flow(make_state, mock_caption):
    raw_input = "ye item whatsapp group mein share karna hai: Blue Kurti"
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input=raw_input, whatsapp_number=phone, reseller_name="Sunita")

    mock_product = {
        "product_id": "SKU-101",
        "name": "Blue Kurti",
        "category": "kurtis",
        "meesho_cost_inr": 300,
        "suggested_selling_price_inr": 499,
        "base_image_url": "https://example.com/blue_kurti.jpg",
        "description": "Cotton printed blue kurti"
    }

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=mock_product) as mock_get_name, \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption) as mock_gen_cap, \
         patch("backend.core.agents.catalog.db_client.log_agent_event") as mock_log:

        res_state = run_catalog_agent(state)

        # Prefix should be stripped for exact-name lookup
        mock_get_name.assert_called_once_with("Blue Kurti")
        mock_gen_cap.assert_called_once()

        # Share trigger copy should be present
        assert "Zaroor Didi! *Blue Kurti* ki cost price ₹300 hai." in res_state["reply_text"]
        assert "WhatsApp group mein ₹499 mein post kar sakte hain" in res_state["reply_text"]
        assert "Kya main isko post kar doon, ya aap price change karna chahengi?" in res_state["reply_text"]
        assert res_state["reply_image_url"] == "https://example.com/blue_kurti.jpg"
        assert res_state["reply_price"] == 499

        # Check pending listing creation
        session_key = _pending_key(phone, "reseller")
        assert session_key in PENDING_LISTINGS
        draft = PENDING_LISTINGS[session_key]
        assert draft["selling_price"] == 499
        assert draft["cost"] == 300
        assert draft["matched_product_name"] == "Blue Kurti"
        assert draft["listing_payload"]["selling_price_inr"] == 499

        mock_log.assert_called_once()
        assert mock_log.call_args[0][0]["event_type"] == "catalog_draft"


def test_catalog_agent_exact_match_standard_listing(make_state, mock_caption):
    raw_input = "Red Banarasi Saree"
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input=raw_input, whatsapp_number=phone)

    mock_product = {
        "product_id": "SKU-202",
        "name": "Red Banarasi Saree",
        "category": "sarees",
        "meesho_cost_inr": 400,
        "suggested_selling_price_inr": 699,
        "base_image_url": "https://example.com/red_saree.jpg",
    }

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=mock_product), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):

        res_state = run_catalog_agent(state)

        assert "Didi, *Red Banarasi Saree* ke liye caption aur price ready hai." in res_state["reply_text"]
        assert "Kya main isey post karun?" in res_state["reply_text"]
        assert res_state["reply_image_url"] == "https://example.com/red_saree.jpg"
        assert res_state["reply_price"] == 699

        session_key = _pending_key(phone, "reseller")
        assert session_key in PENDING_LISTINGS
        assert PENDING_LISTINGS[session_key]["selling_price"] == 699


def test_catalog_agent_custom_price_extraction(make_state, mock_caption):
    # Reseller mentions custom selling price of 799 (> cost 350)
    raw_input = "Cotton Saree 799 me list karo"
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input=raw_input, whatsapp_number=phone)

    mock_product = {
        "product_id": "SKU-303",
        "name": "Cotton Saree",
        "category": "sarees",
        "meesho_cost_inr": 350,
        "suggested_selling_price_inr": 550,
        "base_image_url": "https://example.com/cotton_saree.jpg",
    }

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=mock_product), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):

        res_state = run_catalog_agent(state)

        assert res_state["reply_price"] == 799
        session_key = _pending_key(phone, "reseller")
        assert PENDING_LISTINGS[session_key]["selling_price"] == 799


def test_catalog_agent_ambiguous_results_triggers_picker(make_state):
    raw_input = "acche kurtis dikhao"
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input=raw_input, whatsapp_number=phone)

    candidates = [
        {"product_id": f"K-{i}", "name": f"Kurti {i}", "suggested_selling_price_inr": 400 + i * 50, "meesho_cost_inr": 250}
        for i in range(1, 4)
    ]

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="kurtis"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=candidates), \
         patch("backend.core.agents.catalog.db_client.log_agent_event") as mock_log:

        res_state = run_catalog_agent(state)

        assert "kuch milte-julte options mile hain" in res_state["reply_text"]
        assert res_state["reply_product_options"] is not None
        assert len(res_state["reply_product_options"]) == 3
        assert res_state["reply_image_url"] is None

        session_key = _pending_key(phone, "reseller")
        assert session_key in PENDING_SELECTIONS
        assert PENDING_SELECTIONS[session_key]["agent"] == "catalog"
        assert len(PENDING_SELECTIONS[session_key]["options"]) == 3
        # No draft listing should be created
        assert session_key not in PENDING_LISTINGS

        mock_log.assert_called_once()
        assert mock_log.call_args[0][0]["event_type"] == "catalog_selection_prompt"


def test_catalog_agent_category_exhaustion(make_state):
    phone = "whatsapp:+919876543210"
    session_key = _pending_key(phone, "reseller")
    LAST_REQUESTED_CATEGORY[session_key] = "sarees"
    SHOWN_PRODUCT_IDS[session_key] = ["SKU-1", "SKU-2", "SKU-3"]

    state = make_state(raw_input="aur saree dikhao", whatsapp_number=phone)

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value="sarees"), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=[]), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):

        res_state = run_catalog_agent(state)

        assert "is category mein bas itne hi options uplabdh hain" in res_state["reply_text"]
        assert res_state["reply_product_options"] is None


def test_catalog_agent_no_match_found(make_state):
    phone = "whatsapp:+919876543210"
    state = make_state(raw_input="random product query", whatsapp_number=phone)

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", return_value=None), \
         patch("backend.core.agents.catalog.extract_category_intent", return_value=None), \
         patch("backend.core.agents.catalog.embed_content_with_fallback", return_value=[0.1] * 768), \
         patch("backend.core.agents.catalog.db_client.match_products", return_value=[]), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):

        res_state = run_catalog_agent(state)

        assert "mujhe catalog me is tarah ka koi kapda ya item nahi mila" in res_state["reply_text"]
        session_key = _pending_key(phone, "reseller")
        assert session_key not in PENDING_LISTINGS


def test_catalog_agent_user_isolation(make_state, mock_caption):
    phone_a = "whatsapp:+911111111111"
    phone_b = "whatsapp:+912222222222"

    product_a = {"product_id": "P-A", "name": "Item A", "meesho_cost_inr": 200, "suggested_selling_price_inr": 350}
    product_b = {"product_id": "P-B", "name": "Item B", "meesho_cost_inr": 300, "suggested_selling_price_inr": 500}

    state_a = make_state(raw_input="Item A", whatsapp_number=phone_a)
    state_b = make_state(raw_input="Item B", whatsapp_number=phone_b)

    with patch("backend.core.agents.catalog.db_client.get_product_by_name", side_effect=[product_a, product_b]), \
         patch("backend.core.agents.catalog.generate_whatsapp_caption", return_value=mock_caption), \
         patch("backend.core.agents.catalog.db_client.log_agent_event"):

        run_catalog_agent(state_a)
        run_catalog_agent(state_b)

        key_a = _pending_key(phone_a, "reseller")
        key_b = _pending_key(phone_b, "reseller")

        assert key_a != key_b
        assert PENDING_LISTINGS[key_a]["matched_product_name"] == "Item A"
        assert PENDING_LISTINGS[key_b]["matched_product_name"] == "Item B"
        assert PENDING_LISTINGS[key_a]["selling_price"] == 350
        assert PENDING_LISTINGS[key_b]["selling_price"] == 500
