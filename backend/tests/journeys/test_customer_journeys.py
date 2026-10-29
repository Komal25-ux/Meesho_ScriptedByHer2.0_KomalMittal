"""Whole buyer conversations through the real graph."""
import pytest

from backend.core.constants import DRILL_DOWN_CTA
from backend.core.gemini_utils import CustomerAgentResponse, IntentRouter

from backend.errors import DependencyUnavailable

from backend.tests.support.catalog import PINK_KURTI, WHITE_KURTI


def customer_says(sakhi, **fields):
    reply = dict(ui_text="Ji.", tts_text="जी।", answered_from_product_context=False, return_retention_triggered=False,
                 purchase_intent_detected=False, grounded_via_recent_item=False)
    reply.update(fields)
    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    sakhi.gemini.will_return(CustomerAgentResponse, **reply)


def test_browse_a_category_page_through_it_and_hear_when_it_runs_out(sakhi):
    sakhi.classifiers.category = "kurtis"
    customer_says(sakhi)
    first = sakhi.turn("kurti dikhao")
    assert {o["name"] for o in first["reply_product_options"]} == {PINK_KURTI["name"], WHITE_KURTI["name"]}

    sakhi.classifiers.category = "same"
    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    more = sakhi.turn("aur dikhao")
    assert "bas itne hi options" in more["reply_text"]


def test_pick_a_product_ask_about_it_then_ask_a_follow_up(sakhi):
    customer_says(sakhi)
    sakhi.turn("kurti dikhao")

    # Tapping a picker option answers about that product, with its photo.
    sakhi.gemini.will_return(CustomerAgentResponse, ui_text="Haan, yeh 399 rupaye mein hai.", tts_text="हाँ।",
                             answered_from_product_context=True, return_retention_triggered=False,
                             purchase_intent_detected=False, grounded_via_recent_item=False)
    tapped = sakhi.turn(PINK_KURTI["name"])
    assert tapped["reply_image_url"] == PINK_KURTI["base_image_url"]

    # A follow-up is answered about the same kurti, ending with the order prompt.
    sakhi.classifiers.attribute_followup = True
    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    follow_up = sakhi.turn("kaunse size hain?")
    assert "S, M, L, XL" in follow_up["reply_text"]
    assert follow_up["reply_text"].endswith(DRILL_DOWN_CTA)


def test_saying_yes_twice_after_an_error_places_one_order(sakhi):
    customer_says(sakhi, answered_from_product_context=True)
    sakhi.turn(PINK_KURTI["name"])

    sakhi.db.fail("save_order")
    customer_says(sakhi, purchase_intent_detected=True)
    with pytest.raises(DependencyUnavailable):     # the API answers this with "please retry"
        sakhi.turn("isko order kar do")
    sakhi.db.recover()

    customer_says(sakhi, purchase_intent_detected=True)
    sakhi.turn("isko order kar do")
    customer_says(sakhi, purchase_intent_detected=True)  # impatient third tap
    sakhi.turn("order kar do na")

    assert len(sakhi.db.orders) == 1
