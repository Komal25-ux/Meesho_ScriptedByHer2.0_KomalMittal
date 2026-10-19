import pytest
from unittest.mock import patch

from backend.core.routing.triggers import _strip_trigger_prefix
from backend.core.routing.approval import classify_approval_intent, _extract_price
from backend.core.routing.buying_interest import classify_buying_interest
from backend.core.routing.exchange import classify_exchange_confirmation
from backend.core.routing.returns import classify_return_grievance
from backend.core.routing.category import extract_category_intent
from backend.core.routing.attribute_followup import classify_attribute_followup


# ── TRIGGERS ──────────────────────────────────────────────
def test_strip_trigger_prefix():
    catalog_trigger = "ye item whatsapp group mein share karna hai: Blue Kurti"
    assert _strip_trigger_prefix(catalog_trigger) == "Blue Kurti"

    customer_trigger = "mujhe ye wala item pasand hai, iski details batao: Red Saree"
    assert _strip_trigger_prefix(customer_trigger) == "Red Saree"

    normal_text = "kya haal hai"
    assert _strip_trigger_prefix(normal_text) == "kya haal hai"


# ── APPROVAL ROUTING ──────────────────────────────────────
@pytest.mark.parametrize("text, expected_price", [
    ("haan 599 me kar do", 599),
    ("post at 1200", 1200),
    ("rupaye 450", 450),
    ("price rs. 799", 799),
    ("no price mentioned", None),
])
def test_extract_price(text, expected_price):
    assert _extract_price(text) == expected_price


def test_classify_approval_intent_llm():
    pending = {"matched_product_name": "Silk Saree", "selling_price": 899}

    with patch("backend.core.routing.approval.generate_with_fallback", return_value='{"intent": "approve"}'):
        assert classify_approval_intent("haan kar do", pending) == "approve"

    with patch("backend.core.routing.approval.generate_with_fallback", return_value='```json\n{"intent": "modify"}\n```'):
        assert classify_approval_intent("price 799 kar do", pending) == "modify"

    with patch("backend.core.routing.approval.generate_with_fallback", return_value='{"intent": "new_request"}'):
        assert classify_approval_intent("kuch aur dikhao", pending) == "new_request"


def test_classify_approval_intent_keyword_fallback():
    pending = {"matched_product_name": "Silk Saree", "selling_price": 899}

    with patch("backend.core.routing.approval.generate_with_fallback", return_value=None):
        # Affirmative without price -> approve
        assert classify_approval_intent("haan theek hai", pending) == "approve"
        # Price present -> modify
        assert classify_approval_intent("650 me post karo", pending) == "modify"
        # Negative -> new_request
        assert classify_approval_intent("nahi cancel karo", pending) == "new_request"
        # Ambiguous / other -> new_request
        assert classify_approval_intent("kuch aur baat", pending) == "new_request"


# ── BUYING INTEREST ───────────────────────────────────────
def test_classify_buying_interest():
    with patch("backend.core.routing.buying_interest.generate_with_fallback", return_value='{"interested": true}'):
        assert classify_buying_interest("isko order kar do", "Silk Saree") is True

    with patch("backend.core.routing.buying_interest.generate_with_fallback", return_value='{"interested": false}'):
        assert classify_buying_interest("namaste", "Silk Saree") is False

    # Emergency fallback: keyword-based
    with patch("backend.core.routing.buying_interest.generate_with_fallback", return_value=None):
        assert classify_buying_interest("mujhe ye buy karna hai", "Silk Saree") is True
        assert classify_buying_interest("price kya hai", "Silk Saree") is True
        assert classify_buying_interest("namaste kaise ho", "Silk Saree") is False


# ── EXCHANGE CONFIRMATION ─────────────────────────────────
def test_classify_exchange_confirmation():
    with patch("backend.core.routing.exchange.generate_with_fallback", return_value='{"intent": "accept"}'):
        assert classify_exchange_confirmation("haan exchange karwa do") == "accept"

    with patch("backend.core.routing.exchange.generate_with_fallback", return_value='{"intent": "decline"}'):
        assert classify_exchange_confirmation("nahi mujhe refund chahiye") == "decline"

    # Keyword fallback
    with patch("backend.core.routing.exchange.generate_with_fallback", return_value=None):
        assert classify_exchange_confirmation("theek hai chalega") == "accept"
        assert classify_exchange_confirmation("nahi mat bhejo") == "decline"
        assert classify_exchange_confirmation("kya price hai") == "decline"


# ── RETURN GRIEVANCE ──────────────────────────────────────
def test_classify_return_grievance():
    with patch("backend.core.routing.returns.generate_with_fallback", return_value='{"scenario": "size_issue"}'):
        assert classify_return_grievance("size chhota hai", "Kurti") == "size_issue"

    with patch("backend.core.routing.returns.generate_with_fallback", return_value='{"scenario": "color_style_issue"}'):
        assert classify_return_grievance("color pasand nahi aaya", "Kurti") == "color_style_issue"

    with patch("backend.core.routing.returns.generate_with_fallback", return_value='{"scenario": "defective"}'):
        assert classify_return_grievance("kapda phata hua hai", "Kurti") == "defective"

    with patch("backend.core.routing.returns.generate_with_fallback", return_value='{"scenario": "hard_return"}'):
        assert classify_return_grievance("bas refund de do", "Kurti") == "hard_return"

    # Fallback to keyword matching
    with patch("backend.core.routing.returns.generate_with_fallback", return_value=None):
        assert classify_return_grievance("daag laga hua hai", "Kurti") == "defective"
        assert classify_return_grievance("fit tight hai", "Kurti") == "size_issue"
        assert classify_return_grievance("rang achha nahi laga", "Kurti") == "color_style_issue"
        assert classify_return_grievance("paise wapas karo", "Kurti") == "hard_return"


# ── CATEGORY INTENT ───────────────────────────────────────
def test_extract_category_intent():
    with patch("backend.core.routing.category.generate_with_fallback", return_value='{"category": "sarees"}'):
        assert extract_category_intent("saree dikhao", None) == "sarees"

    with patch("backend.core.routing.category.generate_with_fallback", return_value='{"category": "same"}'):
        assert extract_category_intent("aur dikhao", "kurtis") == "kurtis"

    with patch("backend.core.routing.category.generate_with_fallback", return_value='{"category": "none"}'):
        assert extract_category_intent("namaste", None) is None

    # Keyword fallback when LLM fails
    with patch("backend.core.routing.category.generate_with_fallback", return_value=None):
        assert extract_category_intent("kuch nayi saree dikhao", None) == "sarees"
        assert extract_category_intent("kurti collections", None) == "kurtis"
        # Non-browse words suppress category browse
        assert extract_category_intent("ye saree return karni hai", None) is None
        # Continuation with last_category
        assert extract_category_intent("aur dikhao", "suits") == "suits"


# ── ATTRIBUTE FOLLOWUP ────────────────────────────────────
def test_classify_attribute_followup():
    with patch("backend.core.routing.attribute_followup.generate_with_fallback", return_value='{"is_followup": true}'):
        assert classify_attribute_followup("iska rate kya hai", "Silk Saree") is True

    with patch("backend.core.routing.attribute_followup.generate_with_fallback", return_value='{"is_followup": false}'):
        assert classify_attribute_followup("kuch aur dikhao", "Silk Saree") is False

    # Emergency keyword fallback
    with patch("backend.core.routing.attribute_followup.generate_with_fallback", return_value=None):
        # Attribute query -> True
        assert classify_attribute_followup("size kya hai", "Silk Saree") is True
        assert classify_attribute_followup("fabric cotton hai?", "Silk Saree") is True
        # Complaint query -> False (returns should handle it)
        assert classify_attribute_followup("size chota hai", "Silk Saree") is False
        assert classify_attribute_followup("color pasand nahi", "Silk Saree") is False
        # General tangent -> False
        assert classify_attribute_followup("namaste", "Silk Saree") is False
