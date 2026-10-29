"""The rules each classifier falls back to when Gemini is unreachable.

Each table lists representative inputs per rule, in rule order. Rows marked
"regression" failed before matching became whole-word and refusal-first.
"""
import pytest

from backend.core.routing.approval import classify_approval_intent
from backend.core.routing.attribute_followup import classify_attribute_followup
from backend.core.routing.buying_interest import classify_buying_interest
from backend.core.routing.category import extract_category_intent
from backend.core.routing.exchange import classify_exchange_confirmation
from backend.core.routing.returns import classify_return_grievance

CLASSIFIER_MODULES = [
    "backend.core.routing.approval",
    "backend.core.routing.attribute_followup",
    "backend.core.routing.buying_interest",
    "backend.core.routing.category",
    "backend.core.routing.exchange",
    "backend.core.routing.returns",
]

DRAFT = {"matched_product_name": "Red Banarasi Silk Saree", "selling_price": 599}


@pytest.fixture(autouse=True)
def gemini_unreachable(monkeypatch):
    for module in CLASSIFIER_MODULES:
        monkeypatch.setattr(f"{module}.generate_with_fallback", lambda *_: None)


# Approval of a pending catalog draft
#   price named | refusal | agreement || result
#   yes         | -       | -         || modify
#   no          | yes     | -         || new_request
#   no          | no      | yes       || approve
#   no          | no      | no        || new_request
@pytest.mark.parametrize("reply, intent", [
    ("599 kar do", "modify"),
    ("nahi, 650 me post karo", "modify"),
    ("haan, ₹699 rakho", "modify"),
    ("nahi rehne do", "new_request"),
    ("kal confirm karungi, abhi ruko", "new_request"),  # regression: "confirm" used to approve
    ("theek hai... nahi, cancel", "new_request"),        # regression: agreement was checked first
    ("haan post kar do", "approve"),
    ("post kar do na", "approve"),                       # "na" is "please" here, not "no"
    ("ok", "approve"),
    ("blue kurti dikhao", "new_request"),
    ("book karna hai?", "new_request"),                  # regression: "ok" inside "book"
])
def test_approval_fallback(reply, intent):
    assert classify_approval_intent(reply, DRAFT) == intent


# Reply to an exchange offer: refusal or refund words decline first, then a
# clear yes accepts, and anything unclear declines (refund is the safe default).
@pytest.mark.parametrize("reply, intent", [
    ("haan bhej do", "accept"),
    ("theek hai chalega", "accept"),
    ("exchange kar do", "accept"),
    ("nahi", "decline"),
    ("refund chahiye", "decline"),
    ("exchange nahi chahiye", "decline"),
    ("paise wapas karo", "decline"),
    ("is book ka kya hua", "decline"),                   # regression: "ok" inside "book" accepted
    ("kaunsa colour bhejoge?", "decline"),
])
def test_exchange_fallback(reply, intent):
    assert classify_exchange_confirmation(reply) == intent


# Return grievance: the most serious problem named wins (defect > size > look),
# and naming none means a plain return.
@pytest.mark.parametrize("reply, scenario", [
    ("phata hua aaya aur size bhi chota hai", "defective"),
    ("zip toota hua hai", "defective"),
    ("size chota hai aur rang bhi feeka", "size_issue"),
    ("fitting sahi nahi hai", "size_issue"),
    ("rang pasand nahi aaya", "color_style_issue"),
    ("design achha nahi laga", "color_style_issue"),        # "design" added to the look words
    ("paise wapas karo", "hard_return"),
    ("orange saree hai meri", "hard_return"),            # regression: "rang" inside "orange"
])
def test_return_grievance_fallback(reply, scenario):
    assert classify_return_grievance(reply, "Red Cotton Kurti") == scenario


# Category browse: a return/purchase word vetoes any category, a category word
# browses that category, a "show more" word continues the current one.
@pytest.mark.parametrize("message, current, category", [
    ("saree dikhao", None, "sarees"),
    ("sarees chahiye", None, "sarees"),
    ("koi kurta hai?", None, "kurtis"),
    ("lehnga dikhao", None, "lehengas"),
    ("tops dikhao", None, "tops"),
    ("saree wapas karni hai", None, None),
    ("isko order kar do", "sarees", None),
    ("aur dikhao", "kurtis", "kurtis"),
    ("aur dikhao", None, None),
    ("address change karna hai", None, None),            # regression: "dress"
    ("laptop bag hai?", None, None),                     # regression: "top"
    ("suitable hai kya", None, None),                    # regression: "suit"
])
def test_category_fallback(message, current, category):
    assert extract_category_intent(message, current) == category


# Follow-up question about the product already on screen: a complaint word
# vetoes, otherwise an attribute word makes it a follow-up.
@pytest.mark.parametrize("message, is_followup", [
    ("size kya hai", True),
    ("sizes kaunse hain", True),
    ("colour options?", True),
    ("kitne ka hai", True),
    ("size chota hai", False),
    ("color pasand nahi aaya", False),
    ("namaste", False),
    ("return ho sakta hai kya", False),  # deliberately left to the main flow
])
def test_attribute_followup_fallback(message, is_followup):
    assert classify_attribute_followup(message, "Red Banarasi Silk Saree") is is_followup


@pytest.mark.parametrize("message, interested", [
    ("mujhe ye buy karna hai", True),
    ("kitne ka hai", True),
    ("details bhejo", True),
    ("nahi chahiye", False),             # regression: "chahiye" alone counted as interest
    ("namaste didi", False),
])
def test_buying_interest_fallback(message, interested):
    assert classify_buying_interest(message, "Red Banarasi Silk Saree") is interested
