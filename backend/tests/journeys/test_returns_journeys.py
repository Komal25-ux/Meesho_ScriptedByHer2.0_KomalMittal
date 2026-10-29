"""Returns, from the first message to the hand-off to the reseller."""
from backend.core.agents.returns import run_returns_proactive_outreach
from backend.core.gemini_utils import CustomerAgentResponse, IntentRouter
from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key

from backend.tests.support.catalog import PINK_KURTI, WHITE_KURTI
from backend.tests.support.sessions import SESSION_A

BUYER = _pending_key(SESSION_A, "customer")


def test_a_reported_return_saved_as_an_exchange(sakhi):
    run_returns_proactive_outreach(SESSION_A, "104", WHITE_KURTI["name"])

    sakhi.classifiers.grievance = "size_issue"
    offer = sakhi.turn("size chota hai")
    assert offer["reply_image_url"] == PINK_KURTI["base_image_url"]   # the one-size kurti's alternative
    assert offer["reply_handoff_triggered"] is False

    sakhi.classifiers.exchange = "accept"
    done = sakhi.turn("haan wahi bhej do")

    assert done["reply_handoff_triggered"] is True
    [record] = sakhi.db.returns
    assert (record["reason"], record["resolution"]) == ("size_issue", "exchange_confirmed")
    assert BUYER not in PENDING_RETURNS


def test_a_buyer_complaint_in_chat_starts_the_funnel_and_can_end_in_a_refund(sakhi):
    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    sakhi.gemini.will_return(CustomerAgentResponse, ui_text="Oh! Kya issue hai?", tts_text="ओह!",
                             answered_from_product_context=False, return_retention_triggered=True,
                             purchase_intent_detected=False, grounded_via_recent_item=False)
    sakhi.turn(f"{PINK_KURTI['name']} mein dikkat hai")
    assert PENDING_RETURNS[BUYER]["stage"] == "awaiting_grievance"

    sakhi.classifiers.grievance = "defective"
    sakhi.turn("silai khul gayi hai")
    assert PENDING_RETURNS[BUYER]["grievance"] == "defective"

    sakhi.classifiers.exchange = "decline"
    done = sakhi.turn("nahi, paise wapas chahiye")

    [record] = sakhi.db.returns
    assert (record["reason"], record["resolution"]) == ("defective", "refund_forwarded_after_decline")
    assert done["reply_handoff_triggered"] is True
