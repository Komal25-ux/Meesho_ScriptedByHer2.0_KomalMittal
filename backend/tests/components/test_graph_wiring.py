"""The compiled graph's routing. Gates run in a fixed order before intent
detection, and every agent ends at assemble_reply, which records the turn."""
from backend.core.gemini_utils import IntentRouter
from backend.core.orchestrator import sakhi_orchestrator
from backend.core.session import FRESH_BROADCAST_LOCK, LAST_VIEWED_PRODUCT, PENDING_RETURNS, PENDING_SELECTIONS
from backend.core.state import _pending_key

from backend.tests.support.catalog import GREEN_SUIT, PINK_KURTI
from backend.tests.support.sessions import SESSION_A

BUYER = _pending_key(SESSION_A, "customer")


def test_every_agent_ends_at_assemble_reply():
    edges = set(sakhi_orchestrator.builder.edges)
    for node in ("catalog_agent", "customer_agent", "growth_agent", "general_handler", "finalize_catalog_listing"):
        assert (node, "assemble_reply") in edges
    assert ("assemble_reply", "__end__") in edges


def test_a_return_in_progress_is_handled_before_any_other_pending_state(sakhi):
    PENDING_RETURNS[BUYER] = {"order_id": "104", "product_name": "Pink Cotton Kurti", "reseller_name": "Sunita Didi",
                              "original_product": PINK_KURTI, "stage": "awaiting_grievance"}
    PENDING_SELECTIONS[BUYER] = {"agent": "customer", "options": [{"name": "Pink Cotton Kurti"}]}
    LAST_VIEWED_PRODUCT[BUYER] = GREEN_SUIT
    FRESH_BROADCAST_LOCK[BUYER] = True

    state = sakhi.turn("Pink Cotton Kurti")

    assert state["pending_return_route"] == "handled"
    # Nothing later in the chain ran, so the picker and the lock are untouched.
    assert BUYER in PENDING_SELECTIONS and FRESH_BROADCAST_LOCK[BUYER] is True
    assert sakhi.gemini.prompts[IntentRouter] == []


def test_a_turn_with_nothing_pending_reaches_intent_detection_and_is_recorded(sakhi):
    sakhi.gemini.will_return(IntentRouter, route_to="GENERAL")

    sakhi.turn("namaste")

    assert [t["role"] for t in sakhi.db.turns] == ["user", "assistant"]
    assert all(t["session_id"] == SESSION_A for t in sakhi.db.turns)
