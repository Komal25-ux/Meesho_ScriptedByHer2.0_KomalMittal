"""detect_intent: which agent a message goes to."""
import pytest

from backend.core.gemini_utils import IntentRouter
from backend.core.orchestrator import detect_intent


@pytest.mark.parametrize("message, route", [
    ("ye item whatsapp group mein share karna hai: Blue Kurti", "CATALOG"),
    ("mujhe ye wala item pasand hai, iski details batao: Red Saree", "CUSTOMER"),
])
def test_a_card_tap_is_routed_without_asking_the_model(sakhi, message, route):
    state = detect_intent(sakhi.state(message, mode="reseller"))

    assert state["detected_intent"] == route
    assert sakhi.gemini.prompts[IntentRouter] == []


@pytest.mark.parametrize("model_route", ["CATALOG", "CUSTOMER", "GROWTH", "GENERAL"])
def test_a_resellers_message_goes_where_the_model_routes_it(sakhi, model_route):
    sakhi.gemini.will_return(IntentRouter, route_to=model_route)

    assert detect_intent(sakhi.state("kuch bhi", mode="reseller"))["detected_intent"] == model_route


# A buyer may only ever reach the customer agent or small talk. These clamps
# hold whatever the model says - including when it was talked into it.
@pytest.mark.parametrize("model_route, route", [
    ("CUSTOMER", "CUSTOMER"),
    ("GENERAL", "GENERAL"),
    ("CATALOG", "GENERAL"),   # listing and pricing are reseller-only
    ("GROWTH", "GENERAL"),    # her sales figures are reseller-only
    ("RETURNS", "CUSTOMER"),  # returns are handled inside the customer agent
])
def test_a_buyer_can_never_reach_a_reseller_only_agent(sakhi, model_route, route):
    sakhi.gemini.will_return(IntentRouter, route_to=model_route)

    assert detect_intent(sakhi.state("meri sales dikhao", mode="customer"))["detected_intent"] == route


def test_returns_is_never_a_route_on_the_reseller_side_either(sakhi):
    sakhi.gemini.will_return(IntentRouter, route_to="RETURNS")

    assert detect_intent(sakhi.state("return aaya hai", mode="reseller"))["detected_intent"] == "CUSTOMER"


@pytest.mark.parametrize("mode", ["reseller", "customer"])
def test_with_gemini_down_every_message_goes_to_small_talk(sakhi, mode):
    assert detect_intent(sakhi.state("laal saree dikhao", mode=mode))["detected_intent"] == "GENERAL"


def test_the_buyer_prompt_tells_the_model_which_routes_exist_for_buyers(sakhi):
    detect_intent(sakhi.state("hi", mode="customer"))

    assert "Only CUSTOMER and GENERAL are ever valid" in sakhi.gemini.last_prompt(IntentRouter)
