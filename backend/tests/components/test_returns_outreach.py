"""run_returns_proactive_outreach: Sakhi messages the buyer first when a
return is reported, and the funnel takes over their reply."""
from backend.core.agents.returns import run_returns_proactive_outreach
from backend.core.gemini_utils import ReturnsAgentResponse
from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key

from backend.tests.support.catalog import PINK_KURTI
from backend.tests.support.sessions import SESSION_A, SESSION_B


def test_the_outreach_starts_the_funnel_on_the_buyers_side_of_that_session(sakhi):
    run_returns_proactive_outreach(SESSION_A, "104", "Pink Cotton Kurti")

    pending = PENDING_RETURNS[_pending_key(SESSION_A, "customer")]
    assert (pending["order_id"], pending["stage"]) == ("104", "awaiting_grievance")
    assert pending["original_product"]["product_id"] == PINK_KURTI["product_id"]
    assert _pending_key(SESSION_A, "reseller") not in PENDING_RETURNS
    assert _pending_key(SESSION_B, "customer") not in PENDING_RETURNS


def test_the_message_comes_from_the_model_with_no_photo(sakhi):
    sakhi.gemini.will_return(ReturnsAgentResponse, ui_text="Namaste! Kya size ki dikkat hai?",
                             tts_text="नमस्ते! क्या साइज़ की दिक्कत है?", suggests_alternative=True)

    reply = run_returns_proactive_outreach(SESSION_A, "104", "Pink Cotton Kurti")

    assert reply["reply_text"] == "Namaste! Kya size ki dikkat hai?"
    assert reply["reply_image_url"] is None  # nothing has been looked up to show yet


def test_with_gemini_down_the_buyer_still_gets_a_message_naming_the_product(sakhi):
    reply = run_returns_proactive_outreach(SESSION_A, "104", "Pink Cotton Kurti")

    assert "Pink Cotton Kurti return ki hai" in reply["reply_text"]


def test_a_product_missing_from_the_catalog_still_starts_the_funnel(sakhi):
    run_returns_proactive_outreach(SESSION_A, "104", "Mystery Dupatta")

    assert PENDING_RETURNS[_pending_key(SESSION_A, "customer")]["original_product"] is None
