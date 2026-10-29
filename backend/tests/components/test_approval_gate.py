"""check_pending_approval: her reply to a draft listing waiting for a yes.

   classifier says | price in reply      || route            | draft
   approve         | -                   || finalize         | kept until saved
   modify          | above cost          || price_updated    | re-priced, new caption
   modify          | at/below cost, none || still_pending    | unchanged, asked again
   new_request     | -                   || not_pending      | dropped
   (no draft)      | -                   || not_pending      | -
"""
import pytest

from backend.core.gemini_utils import CatalogCaptionResponse
from backend.core.orchestrator import check_pending_approval
from backend.core.session import PENDING_LISTINGS
from backend.core.state import _pending_key

from backend.tests.support.sessions import SESSION_A

KEY = _pending_key(SESSION_A, "reseller")


def a_draft(price=715, cost=500):
    return {
        "matched_product_name": "White Chikankari Kurti", "matched_product_description": "Lucknowi work",
        "selling_price": price, "cost": cost, "base_image_url": "https://img.example/SKU_011.jpg",
        "listing_payload": {"product_name": "White Chikankari Kurti", "selling_price_inr": price,
                            "cost_price_inr": cost, "whatsapp_caption": "old caption"},
    }


def test_with_no_draft_waiting_the_gate_lets_the_message_through(sakhi):
    state = check_pending_approval(sakhi.state("haan post kar do", mode="reseller"))

    assert state["pending_route"] == "not_pending"
    assert sakhi.classifiers.calls == []  # nothing to classify


def test_a_yes_sends_the_draft_to_be_posted_and_keeps_it_until_it_is_saved(sakhi):
    PENDING_LISTINGS[KEY] = a_draft()
    sakhi.classifiers.approval = "approve"

    state = check_pending_approval(sakhi.state("haan post kar do", mode="reseller"))

    assert state["pending_route"] == "finalize"
    assert PENDING_LISTINGS[KEY] == a_draft()


def test_a_new_price_reprices_the_draft_and_rewrites_the_caption(sakhi):
    PENDING_LISTINGS[KEY] = a_draft()
    sakhi.classifiers.approval = "modify"
    sakhi.gemini.will_return(CatalogCaptionResponse, ui_text="Chikankari kurti sirf ₹799!",
                             tts_text="चिकनकारी कुर्ती 799 रुपये", product_name_tts="चिकनकारी कुर्ती")

    state = check_pending_approval(sakhi.state("799 me kar do", mode="reseller"))

    draft = PENDING_LISTINGS[KEY]
    assert state["pending_route"] == "price_updated"
    assert draft["selling_price"] == 799
    assert draft["listing_payload"]["selling_price_inr"] == 799
    assert draft["listing_payload"]["whatsapp_caption"] == "Chikankari kurti sirf ₹799!"
    assert "profit ₹299" in state["reply_text"]
    assert state["reply_price"] == 799


@pytest.mark.parametrize("reply, accepted", [
    ("499 me kar do", False),   # below cost
    ("500 me kar do", False),   # exactly cost: no profit, not accepted
    ("501 me kar do", True),    # one rupee above cost
])
def test_a_new_price_must_be_above_cost(sakhi, reply, accepted):
    PENDING_LISTINGS[KEY] = a_draft(cost=500)
    sakhi.classifiers.approval = "modify"

    state = check_pending_approval(sakhi.state(reply, mode="reseller"))

    assert (state["pending_route"] == "price_updated") is accepted
    assert (PENDING_LISTINGS[KEY]["selling_price"] != 715) is accepted


def test_a_change_with_no_usable_price_asks_again_and_changes_nothing(sakhi):
    PENDING_LISTINGS[KEY] = a_draft()
    sakhi.classifiers.approval = "modify"

    state = check_pending_approval(sakhi.state("price thoda kam karo", mode="reseller"))

    assert state["pending_route"] == "still_pending"
    assert "naya price kya rakhun" in state["reply_text"]
    assert PENDING_LISTINGS[KEY] == a_draft()


def test_moving_on_to_something_else_drops_the_draft(sakhi):
    PENDING_LISTINGS[KEY] = a_draft()
    sakhi.classifiers.approval = "new_request"

    state = check_pending_approval(sakhi.state("weekly sales dikhao", mode="reseller"))

    assert state["pending_route"] == "not_pending"
    assert KEY not in PENDING_LISTINGS


def test_a_draft_in_the_reseller_pane_does_not_catch_buyer_messages(sakhi):
    PENDING_LISTINGS[KEY] = a_draft()

    state = check_pending_approval(sakhi.state("haan", mode="customer"))

    assert state["pending_route"] == "not_pending"
    assert KEY in PENDING_LISTINGS
