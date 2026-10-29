"""check_pending_return: the returns funnel, as a state machine.

  state                  | buyer says                | product data                      || scenario | next
  awaiting_grievance     | wants a refund            | -                                 || A        | done: refund forwarded
  awaiting_grievance     | size problem              | 2+ sizes                          || B        | awaiting_confirmation (same product)
  awaiting_grievance     | size problem              | 1 size, another in category       || B        | awaiting_confirmation (other product)
  awaiting_grievance     | size problem              | 1 size, nothing else / unknown    || A        | done
  awaiting_grievance     | colour/style problem      | 2+ colours / other / nothing      || C, C, A  | (as for size)
  awaiting_grievance     | defect                    | -                                 || D        | awaiting_confirmation (replacement)
  awaiting_confirmation  | accepts                   | -                                 || E        | done: exchange confirmed
  awaiting_confirmation  | declines                  | -                                 || A        | done: refund after decline

Every "done" saves a return record and hands the conversation to the reseller.
"""
import pytest

from backend.core.gemini_utils import ReturnsAgentResponse
from backend.core.orchestrator import check_pending_return
from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key

from backend.tests.support.catalog import BLUE_SAREE, PINK_KURTI, RED_SAREE, WHITE_KURTI, GREEN_SUIT
from backend.tests.support.sessions import SESSION_A

KEY = _pending_key(SESSION_A, "customer")


def start_return(product, stage="awaiting_grievance", **extra):
    PENDING_RETURNS[KEY] = {"order_id": "104", "product_name": product["name"] if product else "Kurti",
                            "reseller_name": "Sunita Didi", "original_product": product, "stage": stage, **extra}


def scenario(sakhi) -> str:
    prompt = sakhi.gemini.last_prompt(ReturnsAgentResponse)
    return prompt.split("CURRENT STAGE FOR THIS TURN: SCENARIO ")[1][0]


def run(sakhi, text="..."):
    return check_pending_return(sakhi.state(text))


# ── the first reply: what went wrong ─────────────────────────────────

def test_wanting_a_refund_ends_the_funnel_and_hands_off(sakhi):
    start_return(PINK_KURTI)
    sakhi.classifiers.grievance = "hard_return"

    state = run(sakhi, "paise wapas chahiye")

    assert scenario(sakhi) == "A"
    assert KEY not in PENDING_RETURNS
    assert state["reply_handoff_triggered"] is True
    assert sakhi.db.returns[-1]["reason"] == "hard_return"
    assert sakhi.db.returns[-1]["resolution"] == "refund_forwarded"


@pytest.mark.parametrize("grievance, product, offered, label", [
    ("size_issue", PINK_KURTI, PINK_KURTI, "B"),            # S/M/L/XL: offer another size of the same kurti
    ("size_issue", WHITE_KURTI, PINK_KURTI, "B"),           # one size only: offer another kurti
    ("color_style_issue", RED_SAREE, RED_SAREE, "C"),       # red/gold: offer the other colour
    ("color_style_issue", BLUE_SAREE, RED_SAREE, "C"),      # one colour only: offer another saree
])
def test_a_fit_or_look_problem_offers_an_exchange_and_waits(sakhi, grievance, product, offered, label):
    start_return(product)
    sakhi.classifiers.grievance = grievance

    state = run(sakhi)

    pending = PENDING_RETURNS[KEY]
    assert scenario(sakhi) == label
    assert pending["stage"] == "awaiting_confirmation"
    assert pending["grievance"] == grievance
    assert pending["proposed_alternative"]["product_id"] == offered["product_id"]
    assert state["reply_handoff_triggered"] is False


@pytest.mark.parametrize("grievance", ["size_issue", "color_style_issue"])
def test_with_nothing_to_offer_a_fit_or_look_problem_becomes_a_refund(sakhi, grievance):
    start_return(GREEN_SUIT)                    # the only suit, one colour
    sakhi.classifiers.grievance = grievance
    if grievance == "size_issue":
        PENDING_RETURNS[KEY] = dict(PENDING_RETURNS[KEY], original_product=dict(GREEN_SUIT, sizes=["M"]))

    run(sakhi)

    assert scenario(sakhi) == "A"
    assert KEY not in PENDING_RETURNS


def test_a_return_for_a_product_not_in_the_catalog_becomes_a_refund(sakhi):
    start_return(None)
    sakhi.classifiers.grievance = "size_issue"

    run(sakhi)

    assert scenario(sakhi) == "A"


def test_a_defect_offers_a_replacement_of_the_same_product(sakhi):
    start_return(PINK_KURTI)
    sakhi.classifiers.grievance = "defective"

    state = run(sakhi, "phata hua aaya")

    assert scenario(sakhi) == "D"
    assert PENDING_RETURNS[KEY]["proposed_alternative"]["product_id"] == PINK_KURTI["product_id"]
    assert state["reply_image_url"] is None  # nothing new to show for a replacement


# ── the second reply: the exchange offer ─────────────────────────────

def test_accepting_the_exchange_confirms_it_and_hands_off(sakhi):
    start_return(PINK_KURTI, stage="awaiting_confirmation", grievance="size_issue", proposed_alternative=PINK_KURTI)
    sakhi.classifiers.exchange = "accept"

    state = run(sakhi, "haan bhej do")

    assert scenario(sakhi) == "E"
    assert sakhi.db.returns[-1]["resolution"] == "exchange_confirmed"
    assert sakhi.db.returns[-1]["reason"] == "size_issue"
    assert state["reply_handoff_triggered"] is True
    assert KEY not in PENDING_RETURNS


def test_declining_the_exchange_forwards_the_refund(sakhi):
    start_return(PINK_KURTI, stage="awaiting_confirmation", grievance="color_style_issue", proposed_alternative=PINK_KURTI)
    sakhi.classifiers.exchange = "decline"

    run(sakhi, "nahi, refund do")

    assert scenario(sakhi) == "A"
    assert sakhi.db.returns[-1]["resolution"] == "refund_forwarded_after_decline"


# ── what the buyer sees ──────────────────────────────────────────────

def test_an_exchange_offer_shows_the_offered_product_when_the_reply_names_it(sakhi):
    start_return(WHITE_KURTI)
    sakhi.classifiers.grievance = "size_issue"
    sakhi.gemini.will_return(ReturnsAgentResponse, ui_text="Pink Cotton Kurti try karein? 399 rupaye.",
                             tts_text="पिंक कॉटन कुर्ती?", suggests_alternative=True)

    state = run(sakhi)

    assert state["reply_image_url"] == PINK_KURTI["base_image_url"]


def test_no_photo_when_the_reply_does_not_actually_name_the_offer(sakhi):
    start_return(WHITE_KURTI)
    sakhi.classifiers.grievance = "size_issue"
    sakhi.gemini.will_return(ReturnsAgentResponse, ui_text="Hum exchange karwa denge.", tts_text="हम एक्सचेंज करवा देंगे।",
                             suggests_alternative=False)

    assert run(sakhi)["reply_image_url"] is None


def test_with_gemini_down_the_buyer_gets_the_fixed_text_for_the_scenario(sakhi):
    start_return(PINK_KURTI)
    sakhi.classifiers.grievance = "defective"

    state = run(sakhi)

    assert state["reply_text"].startswith("Oh no! Maaf kijiyega ki aapko kharab product mila.")


def test_the_reseller_pane_is_never_pulled_into_a_buyers_return(sakhi):
    start_return(PINK_KURTI)

    state = check_pending_return(sakhi.state("haan", mode="reseller"))

    assert state["pending_return_route"] == "not_pending"
    assert KEY in PENDING_RETURNS
