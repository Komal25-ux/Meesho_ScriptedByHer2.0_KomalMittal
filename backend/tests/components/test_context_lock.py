"""check_fresh_context_lock: a buyer's first reply right after a listing is
posted binds to that listing, once."""
from backend.core.gemini_utils import CustomerAgentResponse
from backend.core.orchestrator import check_fresh_context_lock
from backend.core.session import FRESH_BROADCAST_LOCK, LAST_VIEWED_PRODUCT
from backend.core.state import _pending_key

from backend.tests.support.catalog import GREEN_SUIT
from backend.tests.support.sessions import SESSION_A

KEY = _pending_key(SESSION_A, "customer")


def just_posted(product=GREEN_SUIT, price=1100):
    LAST_VIEWED_PRODUCT[KEY] = dict(product, suggested_selling_price_inr=price)
    FRESH_BROADCAST_LOCK[KEY] = True


def test_interest_right_after_a_post_is_answered_about_that_post(sakhi):
    just_posted()
    sakhi.classifiers.buying_interest = True
    sakhi.gemini.will_return(CustomerAgentResponse, ui_text="Green Anarkali Suit 1100 rupaye ka hai. Order karun?",
                             tts_text="ग्रीन अनारकली सूट 1100 रुपये का है।", answered_from_product_context=True,
                             return_retention_triggered=False, purchase_intent_detected=False,
                             grounded_via_recent_item=True)

    state = check_fresh_context_lock(sakhi.state("I want to buy"))

    assert state["context_lock_route"] == "handled"
    assert state["reply_image_url"] == GREEN_SUIT["base_image_url"]
    assert "1100" in state["reply_text"]


def test_with_gemini_down_the_buyer_still_gets_the_posted_price(sakhi):
    just_posted(price=1100)
    sakhi.classifiers.buying_interest = True

    state = check_fresh_context_lock(sakhi.state("details bhejo"))

    assert "₹1100" in state["reply_text"]
    assert "order place kar doon" in state["reply_text"]


def test_the_lock_is_used_up_by_the_first_reply_even_without_interest(sakhi):
    just_posted()
    sakhi.classifiers.buying_interest = False

    state = check_fresh_context_lock(sakhi.state("namaste"))

    assert state["context_lock_route"] == "not_locked"
    assert KEY not in FRESH_BROADCAST_LOCK


def test_without_a_fresh_post_there_is_nothing_to_bind_to(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = GREEN_SUIT
    sakhi.classifiers.buying_interest = True

    state = check_fresh_context_lock(sakhi.state("I want to buy"))

    assert state["context_lock_route"] == "not_locked"
    assert sakhi.classifiers.calls == []


def test_a_reseller_message_never_spends_the_buyers_lock(sakhi):
    just_posted()

    check_fresh_context_lock(sakhi.state("I want to buy", mode="reseller"))

    assert FRESH_BROADCAST_LOCK[KEY] is True
