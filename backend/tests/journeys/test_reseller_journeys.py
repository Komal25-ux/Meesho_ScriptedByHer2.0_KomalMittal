"""Whole reseller conversations, message by message, through the real graph."""
from backend.core.gemini_utils import AgentResponse, CustomerAgentResponse, IntentRouter
from backend.core.session import PENDING_LISTINGS
from backend.core.state import _pending_key

from backend.tests.support.catalog import BLUE_SAREE
from backend.tests.support.sessions import SESSION_A

RESELLER = _pending_key(SESSION_A, "reseller")


def test_from_browsing_to_a_buyers_order_at_the_price_she_negotiated(sakhi):
    # She asks to list a saree and gets a picker.
    sakhi.gemini.will_return(IntentRouter, route_to="CATALOG")
    picker = sakhi.turn("saree list karni hai", mode="reseller")
    assert BLUE_SAREE["name"] in [o["name"] for o in picker["reply_product_options"]]

    # She taps the blue one: a draft at the catalog price, waiting for her.
    draft = sakhi.turn(BLUE_SAREE["name"], mode="reseller")
    assert draft["reply_price"] == 549

    # She wants more for it.
    sakhi.classifiers.approval = "modify"
    repriced = sakhi.turn("nahi, 599 me kar do", mode="reseller")
    assert repriced["reply_price"] == 599

    # She says yes: it is listed and broadcast.
    sakhi.classifiers.approval = "approve"
    posted = sakhi.turn("haan post kar do", mode="reseller")
    assert posted["listing_finalized"] is True
    [listing] = sakhi.db.listings
    assert listing["selling_price_inr"] == 599

    # A buyer reacts to the post and is told her price.
    sakhi.classifiers.buying_interest = True
    interest = sakhi.turn("I want to buy", mode="customer")
    assert "₹599" in interest["reply_text"]

    # The buyer confirms; one order, at her price, against her listing.
    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    sakhi.gemini.will_return(CustomerAgentResponse, ui_text="Ji zaroor!", tts_text="जी ज़रूर!",
                             answered_from_product_context=False, return_retention_triggered=False,
                             purchase_intent_detected=True, grounded_via_recent_item=False)
    ordered = sakhi.turn("isko order kar do", mode="customer")
    [order] = sakhi.db.orders
    assert (order["product_id"], order["unit_price_inr"], order["listing_id"]) == (BLUE_SAREE["product_id"], 599, listing["id"])
    assert ordered["reply_confirmed_product_is_unlisted"] is False


def test_moving_on_from_a_draft_drops_it_and_answers_the_new_request(sakhi):
    sakhi.gemini.will_return(IntentRouter, route_to="CATALOG")
    sakhi.turn(BLUE_SAREE["name"], mode="reseller")
    assert RESELLER in PENDING_LISTINGS

    sakhi.classifiers.approval = "new_request"
    sakhi.gemini.will_return(IntentRouter, route_to="GROWTH")
    sakhi.gemini.will_return(AgentResponse, ui_text="Is hafte ki sales...", tts_text="इस हफ्ते की सेल्स")
    reply = sakhi.turn("weekly sales dikhao", mode="reseller")

    assert RESELLER not in PENDING_LISTINGS
    assert reply["detected_intent"] == "GROWTH"
    assert sakhi.db.listings == []
