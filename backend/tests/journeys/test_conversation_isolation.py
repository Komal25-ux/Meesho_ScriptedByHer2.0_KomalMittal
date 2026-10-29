"""Two visitors on the demo at once are both "Sunita Didi", and one browser
tab drives both panes. Nothing may leak between conversations or panes."""
from backend.core.gemini_utils import CustomerAgentResponse, IntentRouter
from backend.core.session import LAST_VIEWED_PRODUCT, PENDING_LISTINGS, PENDING_SELECTIONS
from backend.core.state import _pending_key

from backend.tests.support.catalog import BLUE_SAREE, PINK_KURTI
from backend.tests.support.sessions import SESSION_A, SESSION_B


def browse(sakhi, text, session):
    sakhi.gemini.will_return(IntentRouter, route_to="CATALOG")
    return sakhi.turn(text, mode="reseller", session=session)


def test_interleaved_visitors_each_keep_their_own_picker(sakhi):
    browse(sakhi, "saree list karni hai", SESSION_A)
    browse(sakhi, "kurti list karni hai", SESSION_B)

    # A taps an option from A's picker; B's picker is untouched.
    sakhi.turn(BLUE_SAREE["name"], mode="reseller", session=SESSION_A)

    assert PENDING_LISTINGS[_pending_key(SESSION_A, "reseller")]["matched_product_name"] == BLUE_SAREE["name"]
    b_picker = PENDING_SELECTIONS[_pending_key(SESSION_B, "reseller")]
    assert {o["name"] for o in b_picker["options"]} == {PINK_KURTI["name"], "White Chikankari Kurti"}
    assert _pending_key(SESSION_B, "reseller") not in PENDING_LISTINGS


def test_one_visitors_yes_never_posts_another_visitors_draft(sakhi):
    browse(sakhi, BLUE_SAREE["name"], SESSION_A)          # A has a draft waiting

    sakhi.classifiers.approval = "approve"
    sakhi.gemini.will_return(IntentRouter, route_to="GENERAL")
    sakhi.turn("haan post kar do", mode="reseller", session=SESSION_B)   # B says yes to nothing

    assert sakhi.db.listings == []
    assert _pending_key(SESSION_A, "reseller") in PENDING_LISTINGS


def test_a_draft_in_the_reseller_pane_is_invisible_to_the_buyer_pane(sakhi):
    browse(sakhi, BLUE_SAREE["name"], SESSION_A)

    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    sakhi.gemini.will_return(CustomerAgentResponse, ui_text="Haan, 399 rupaye.", tts_text="हाँ।",
                             answered_from_product_context=True, return_retention_triggered=False,
                             purchase_intent_detected=False, grounded_via_recent_item=False)
    sakhi.turn(PINK_KURTI["name"], mode="customer", session=SESSION_A)

    assert PENDING_LISTINGS[_pending_key(SESSION_A, "reseller")]["matched_product_name"] == BLUE_SAREE["name"]
    assert LAST_VIEWED_PRODUCT[_pending_key(SESSION_A, "customer")]["product_id"] == PINK_KURTI["product_id"]
    assert _pending_key(SESSION_A, "reseller") not in LAST_VIEWED_PRODUCT


def test_over_http_two_tabs_with_the_same_number_are_two_conversations(api_client, sakhi):
    # The original bug: every browser sent one hard-coded number and the
    # backend keyed conversations on it, so tab B's "yes" posted tab A's draft.
    def post(session, text):
        return api_client.post("/api/v1/chat/send", data={
            "session_id": session, "whatsapp_number": "whatsapp:+919876543210",
            "active_mode": "reseller", "text_message": text})

    sakhi.gemini.will_return(IntentRouter, route_to="CATALOG")
    post(SESSION_A, BLUE_SAREE["name"])

    sakhi.classifiers.approval = "approve"
    sakhi.gemini.will_return(IntentRouter, route_to="GENERAL")
    post(SESSION_B, "haan post kar do")

    assert sakhi.db.listings == []
    assert _pending_key(SESSION_A, "reseller") in PENDING_LISTINGS
