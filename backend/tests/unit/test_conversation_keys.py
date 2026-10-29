"""How a turn is tied to its conversation (backend/core/state.py)."""
from backend.core.state import _pending_key, conversation_id, new_turn_state

from backend.tests.support.sessions import DEMO_NUMBER, SESSION_A, SESSION_B


def test_a_conversation_is_the_browser_session_not_the_phone_number():
    # Both visitors are the same demo reseller; only the session tells them apart.
    a = new_turn_state(SESSION_A, DEMO_NUMBER, "hi")
    b = new_turn_state(SESSION_B, DEMO_NUMBER, "hi")

    assert conversation_id(a) != conversation_id(b)


def test_the_two_panes_of_one_session_keep_separate_state():
    assert _pending_key(SESSION_A, "reseller") != _pending_key(SESSION_A, "customer")


def test_without_a_session_the_number_is_the_fallback():
    # Only code paths that never came through the API (scripts) lack one.
    state = new_turn_state(None, DEMO_NUMBER, "hi")
    assert conversation_id(state) == DEMO_NUMBER


def test_a_new_turn_starts_with_nothing_decided():
    state = new_turn_state(SESSION_A, DEMO_NUMBER, "hi", active_mode="customer", client_message_id="m-1")

    assert (state["raw_input"], state["active_mode"], state["client_message_id"]) == ("hi", "customer", "m-1")
    assert state["trace_logs"] == []
    assert not state["listing_finalized"] and not state["reply_purchase_intent_detected"]
    assert state["reply_text"] == "" and state["reply_image_url"] is None
