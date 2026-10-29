"""run_customer_agent: one buyer message, from search to reply.

Branches, in the order the agent takes them:
  drill-down follow-up on the product already on screen  (short-circuits everything)
  category browse exhausted                               (no model call)
  purchase confirmed                                      (order saved, no picker)
  2+ candidates and no grounded answer                    (picker)
  otherwise: the model's reply, with an image only when grounded
"""
import pytest

from backend.core.agents.customer import run_customer_agent
from backend.core.constants import CUSTOMER_ZERO_HALLUCINATION_REFUSAL, DRILL_DOWN_CTA
from backend.core.gemini_utils import CustomerAgentResponse
from backend.core.pricing import suggested_price
from backend.core.session import (
    LAST_REQUESTED_CATEGORY, LAST_VIEWED_PRODUCT, PENDING_RETURNS, PENDING_SELECTIONS, SHOWN_PRODUCT_IDS,
)
from backend.core.state import _pending_key
from backend.errors import DependencyUnavailable

from backend.tests.support.catalog import BLUE_SAREE, PINK_KURTI, RED_SAREE, YELLOW_SAREE
from backend.tests.support.sessions import SESSION_A

KEY = _pending_key(SESSION_A, "customer")


def model_replies(sakhi, **overrides):
    fields = dict(
        ui_text="Ji, yeh available hai.", tts_text="जी, यह उपलब्ध है।",
        answered_from_product_context=False, return_retention_triggered=False,
        purchase_intent_detected=False, grounded_via_recent_item=False,
    )
    fields.update(overrides)
    sakhi.gemini.will_return(CustomerAgentResponse, **fields)


def prompt_sent(sakhi) -> str:
    return sakhi.gemini.last_prompt(CustomerAgentResponse)


# ── which price a buyer is quoted ────────────────────────────────────
#   listed by the reseller?  | catalog price? || quoted
#   yes                      | -              || her listed price
#   no                       | yes            || the catalog price (what her draft would say)
#   no                       | no             || the cost rule

def test_a_listed_product_is_quoted_at_the_resellers_own_price(sakhi):
    sakhi.db.list_product(RED_SAREE["product_id"], price=650)
    model_replies(sakhi)

    run_customer_agent(sakhi.state(RED_SAREE["name"]))

    assert "Price: 650 rupaye" in prompt_sent(sakhi)


def test_an_unlisted_product_is_quoted_at_the_catalog_price(sakhi):
    model_replies(sakhi)

    run_customer_agent(sakhi.state(RED_SAREE["name"]))

    assert "Price: 599 rupaye" in prompt_sent(sakhi)


def test_an_unlisted_product_with_no_catalog_price_falls_back_to_the_cost_rule(sakhi):
    sakhi.db.products[PINK_KURTI["product_id"]]["suggested_selling_price_inr"] = None
    model_replies(sakhi)

    run_customer_agent(sakhi.state(PINK_KURTI["name"]))

    assert f"Price: {suggested_price(PINK_KURTI['meesho_cost_inr'])} rupaye" in prompt_sent(sakhi)


# ── a grounded answer ────────────────────────────────────────────────

def test_a_grounded_answer_shows_the_product_photo_and_remembers_the_product(sakhi):
    model_replies(sakhi, ui_text="Haan, yeh 599 rupaye mein hai.", tts_text="हाँ, यह 599 रुपये में है।",
                  answered_from_product_context=True)

    state = run_customer_agent(sakhi.state(RED_SAREE["name"]))

    assert state["reply_text"] == "Haan, yeh 599 rupaye mein hai."
    assert state["reply_image_url"] == RED_SAREE["base_image_url"]
    assert LAST_VIEWED_PRODUCT[KEY]["product_id"] == RED_SAREE["product_id"]


def test_an_ungrounded_answer_shows_no_photo_and_remembers_nothing(sakhi):
    model_replies(sakhi, ui_text=CUSTOMER_ZERO_HALLUCINATION_REFUSAL, answered_from_product_context=False)

    state = run_customer_agent(sakhi.state(RED_SAREE["name"] + " ka blouse size?"))

    assert state["reply_image_url"] is None
    assert KEY not in LAST_VIEWED_PRODUCT


def test_with_gemini_down_the_buyer_gets_the_refusal_not_a_guess(sakhi):
    state = run_customer_agent(sakhi.state(RED_SAREE["name"]))

    assert state["reply_text"] == CUSTOMER_ZERO_HALLUCINATION_REFUSAL
    assert state["reply_image_url"] is None


def test_a_card_tap_is_looked_up_by_exact_name_and_flagged_to_the_model(sakhi):
    model_replies(sakhi, answered_from_product_context=True)

    run_customer_agent(sakhi.state(f"mujhe ye wala item pasand hai, iski details batao: {BLUE_SAREE['name']}"))

    prompt = prompt_sent(sakhi)
    assert "PRODUCT_CARD_CLICK: true" in prompt
    assert f"Product: {BLUE_SAREE['name']}" in prompt
    assert RED_SAREE["name"] not in prompt  # exact lookup, not a fuzzy search


# ── the picker ───────────────────────────────────────────────────────

def test_an_ambiguous_search_shows_a_picker_instead_of_a_wall_of_text(sakhi):
    model_replies(sakhi, answered_from_product_context=False)

    state = run_customer_agent(sakhi.state("saree dikhao"))

    names = [o["name"] for o in state["reply_product_options"]]
    assert names == [RED_SAREE["name"], BLUE_SAREE["name"], YELLOW_SAREE["name"]]
    assert PENDING_SELECTIONS[KEY]["agent"] == "customer"
    assert state["reply_image_url"] is None


def test_a_picker_never_has_more_than_four_options(sakhi):
    for n in range(4):
        sakhi.db.products[f"SKU_9{n}"] = dict(RED_SAREE, product_id=f"SKU_9{n}", name=f"Extra Saree {n}")
    model_replies(sakhi)

    state = run_customer_agent(sakhi.state("saree"))

    assert len(state["reply_product_options"]) == 4


def test_a_category_browse_remembers_what_it_showed_so_more_never_repeats(sakhi):
    sakhi.classifiers.category = "sarees"
    model_replies(sakhi)
    first = run_customer_agent(sakhi.state("saree dikhao"))

    sakhi.classifiers.category = "same"
    model_replies(sakhi)
    second = run_customer_agent(sakhi.state("aur dikhao"))

    first_ids = {o["name"] for o in first["reply_product_options"]}
    second_ids = {o["name"] for o in (second["reply_product_options"] or [])}
    assert first_ids and not first_ids & second_ids
    assert LAST_REQUESTED_CATEGORY[KEY] == "sarees"


def test_a_category_browse_that_has_shown_everything_says_so_without_asking_the_model(sakhi):
    sakhi.classifiers.category = "sarees"
    LAST_REQUESTED_CATEGORY[KEY] = "sarees"
    SHOWN_PRODUCT_IDS[KEY] = [RED_SAREE["product_id"], BLUE_SAREE["product_id"], YELLOW_SAREE["product_id"]]

    state = run_customer_agent(sakhi.state("aur dikhao"))

    assert "bas itne hi options" in state["reply_text"]
    assert sakhi.gemini.prompts[CustomerAgentResponse] == []


def test_switching_category_starts_its_pagination_afresh(sakhi):
    LAST_REQUESTED_CATEGORY[KEY] = "sarees"
    SHOWN_PRODUCT_IDS[KEY] = [RED_SAREE["product_id"]]
    sakhi.classifiers.category = "kurtis"
    model_replies(sakhi)

    run_customer_agent(sakhi.state("kurti dikhao"))

    assert SHOWN_PRODUCT_IDS[KEY] == ["SKU_010", "SKU_011"]


# ── purchase confirmation ────────────────────────────────────────────

def test_an_order_is_for_the_product_on_screen_not_whatever_this_message_matched(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = BLUE_SAREE
    model_replies(sakhi, purchase_intent_detected=True)

    state = run_customer_agent(sakhi.state("red wali nahi, isko order kar do"))  # "red" matches the red saree

    [order] = sakhi.db.orders
    assert order["product_id"] == BLUE_SAREE["product_id"]
    assert order["unit_price_inr"] == BLUE_SAREE["suggested_selling_price_inr"]
    assert state["reply_order_id"] == order["id"]
    assert state["reply_confirmed_product_name"] == BLUE_SAREE["name"]


def test_an_order_records_whether_the_reseller_had_listed_the_product(sakhi):
    listing = sakhi.db.list_product(BLUE_SAREE["product_id"], price=575)
    LAST_VIEWED_PRODUCT[KEY] = BLUE_SAREE
    model_replies(sakhi, purchase_intent_detected=True)

    state = run_customer_agent(sakhi.state("isko order kar do"))

    [order] = sakhi.db.orders
    assert order["listing_id"] == listing["id"]
    assert order["unit_price_inr"] == 575
    assert state["reply_confirmed_product_is_unlisted"] is False


def test_after_ordering_the_product_is_forgotten_so_the_next_yes_is_not_a_second_order(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = BLUE_SAREE
    model_replies(sakhi, purchase_intent_detected=True)

    run_customer_agent(sakhi.state("isko order kar do"))

    assert KEY not in LAST_VIEWED_PRODUCT


def test_an_order_with_nothing_to_refer_to_saves_nothing(sakhi):
    model_replies(sakhi, purchase_intent_detected=True)  # the model says yes, but to what?

    state = run_customer_agent(sakhi.state("ye lena hai"))

    assert sakhi.db.orders == []
    assert state["reply_order_id"] is None
    assert state["reply_confirmed_product_name"] is None


def test_a_failed_order_save_fails_the_turn_and_keeps_the_product_for_a_retry(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = BLUE_SAREE
    sakhi.db.fail("save_order")
    model_replies(sakhi, purchase_intent_detected=True)

    with pytest.raises(DependencyUnavailable):
        run_customer_agent(sakhi.state("isko order kar do"))

    assert LAST_VIEWED_PRODUCT[KEY]["product_id"] == BLUE_SAREE["product_id"]


# ── returns ──────────────────────────────────────────────────────────

def test_a_return_complaint_starts_the_returns_funnel_for_the_next_message(sakhi):
    model_replies(sakhi, return_retention_triggered=True)

    run_customer_agent(sakhi.state(f"{RED_SAREE['name']} ka size chota hai"))

    pending = PENDING_RETURNS[KEY]
    assert pending["stage"] == "awaiting_grievance"
    assert pending["original_product"]["product_id"] == RED_SAREE["product_id"]


def test_a_return_complaint_never_shows_a_picker(sakhi):
    model_replies(sakhi, return_retention_triggered=True)

    state = run_customer_agent(sakhi.state("saree wapas karni hai"))  # matches all three sarees

    assert state["reply_product_options"] is None


# ── follow-up questions about the product on screen ─────────────────

def test_a_follow_up_question_is_answered_about_the_product_on_screen_only(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = PINK_KURTI
    sakhi.classifiers.attribute_followup = True
    model_replies(sakhi, ui_text="Isme S, M, L, XL sizes hain.", answered_from_product_context=True,
                  grounded_via_recent_item=True)

    state = run_customer_agent(sakhi.state("saree jaisa size chart hai kya?"))

    assert "category" not in [name for name, _ in sakhi.classifiers.calls]  # no new search started
    assert PINK_KURTI["name"] in prompt_sent(sakhi)
    assert state["reply_text"].endswith(DRILL_DOWN_CTA)
    assert state["reply_image_url"] is None


def test_with_gemini_down_a_follow_up_still_lists_the_real_sizes(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = PINK_KURTI
    sakhi.classifiers.attribute_followup = True

    state = run_customer_agent(sakhi.state("size kya hai"))

    assert "S, M, L, XL" in state["reply_text"]
    assert state["reply_text"].endswith(DRILL_DOWN_CTA)


def test_a_pronoun_answer_takes_its_photo_from_the_product_on_screen_not_this_search(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = PINK_KURTI
    model_replies(sakhi, answered_from_product_context=True, grounded_via_recent_item=True)

    state = run_customer_agent(sakhi.state("red colour mein bhi hai?"))  # "red" matches the red saree

    assert state["reply_image_url"] is None  # a drill-down never shows a photo
    assert state["reply_text"].endswith(DRILL_DOWN_CTA)
    assert LAST_VIEWED_PRODUCT[KEY]["product_id"] == PINK_KURTI["product_id"]


def test_a_follow_up_quotes_the_price_she_listed_at_since_the_product_was_viewed(sakhi):
    LAST_VIEWED_PRODUCT[KEY] = PINK_KURTI          # viewed while unlisted, at ₹399
    sakhi.db.list_product(PINK_KURTI["product_id"], price=449)
    sakhi.classifiers.attribute_followup = True
    model_replies(sakhi, ui_text="Yeh 449 rupaye ki hai.", tts_text="यह 449 रुपये की है।",
                  answered_from_product_context=True, grounded_via_recent_item=True)

    state = run_customer_agent(sakhi.state("kitne ki hai?"))

    assert "449 rupaye" in state["reply_text"]


# ── duplicate orders ─────────────────────────────────────────────────

def confirm_order(sakhi, product=BLUE_SAREE, session=SESSION_A, message_id=None):
    LAST_VIEWED_PRODUCT[_pending_key(session, "customer")] = product
    model_replies(sakhi, purchase_intent_detected=True)
    state = sakhi.state("isko order kar do", session=session)
    state["client_message_id"] = message_id
    return run_customer_agent(state)


def test_a_retried_request_returns_the_order_it_already_created(sakhi):
    first = confirm_order(sakhi, message_id="0d4f6a8c-1e3a-4c5e-9a7c-2e4f6a8c0e1a")
    sakhi.db.clock = sakhi.db.clock.replace(year=2027)  # far outside the repeat window, so only the id can match

    again = confirm_order(sakhi, message_id="0d4f6a8c-1e3a-4c5e-9a7c-2e4f6a8c0e1a")

    assert len(sakhi.db.orders) == 1
    assert again["reply_order_id"] == first["reply_order_id"]


@pytest.mark.parametrize("minutes_later, orders", [
    (0, 1),
    (9.99, 1),    # inside the 10-minute repeat window: the same order
    (10, 1),      # the window is inclusive
    (10.01, 2),   # outside it: a genuine second order
])
def test_a_retyped_confirmation_within_ten_minutes_is_the_same_order(sakhi, minutes_later, orders):
    from datetime import timedelta
    confirm_order(sakhi, message_id="1a1a1a1a-1a1a-4a1a-8a1a-1a1a1a1a1a1a")
    sakhi.db.clock += timedelta(minutes=minutes_later)

    confirm_order(sakhi, message_id="2b2b2b2b-2b2b-4b2b-8b2b-2b2b2b2b2b2b")

    assert len(sakhi.db.orders) == orders


def test_a_different_product_is_always_a_new_order(sakhi):
    confirm_order(sakhi, product=BLUE_SAREE)
    confirm_order(sakhi, product=RED_SAREE)

    assert [o["product_id"] for o in sakhi.db.orders] == [BLUE_SAREE["product_id"], RED_SAREE["product_id"]]


def test_two_visitors_ordering_the_same_product_get_two_orders(sakhi):
    from backend.tests.support.sessions import SESSION_B
    confirm_order(sakhi, session=SESSION_A)
    confirm_order(sakhi, session=SESSION_B)

    assert len(sakhi.db.orders) == 2
