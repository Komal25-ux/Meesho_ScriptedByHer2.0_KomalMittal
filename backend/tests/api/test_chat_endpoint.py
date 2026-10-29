"""POST /api/v1/chat/send - what the frontend gets back.

These run the real graph on the fakes, so a response field is checked
against what the agents actually did, not against a hand-written result.
"""
import base64
import io

import pytest

from backend.core.gemini_utils import CustomerAgentResponse, IntentRouter
from backend.core.session import LAST_VIEWED_PRODUCT, PENDING_LISTINGS
from backend.core.state import _pending_key

from backend.tests.support.catalog import BLUE_SAREE, GREEN_SUIT, PINK_KURTI
from backend.tests.support.sessions import DEMO_NUMBER, SESSION_A


def send(api_client, text, mode="customer", **extra):
    return api_client.post("/api/v1/chat/send", data={
        "session_id": SESSION_A, "text_message": text, "active_mode": mode, "whatsapp_number": DEMO_NUMBER, **extra})


def heard(response_audio):
    return base64.b64decode(response_audio).decode()


def customer_reply(sakhi, **fields):
    reply = dict(ui_text="Ji.", tts_text="जी।", answered_from_product_context=False, return_retention_triggered=False,
                 purchase_intent_detected=False, grounded_via_recent_item=False)
    reply.update(fields)
    sakhi.gemini.will_return(IntentRouter, route_to="CUSTOMER")
    sakhi.gemini.will_return(CustomerAgentResponse, **reply)


# ── what a reply carries ─────────────────────────────────────────────

def test_a_grounded_answer_comes_back_as_text_voice_and_photo(api_client, sakhi):
    customer_reply(sakhi, ui_text="Haan, 399 rupaye.", tts_text="हाँ, 399 रुपये।", answered_from_product_context=True)

    body = send(api_client, PINK_KURTI["name"]).json()

    assert body["text"] == "Haan, 399 rupaye."
    assert heard(body["audio"]) == "audio:हाँ, 399 रुपये।"     # the Devanagari text is what is spoken
    assert body["image_url"] == PINK_KURTI["base_image_url"]
    assert body["voice_fallback"] is False
    assert body["product_options"] is None


def test_an_ambiguous_question_comes_back_as_picker_options(api_client, sakhi):
    customer_reply(sakhi)

    body = send(api_client, "saree dikhao").json()

    assert [o["name"] for o in body["product_options"]][:2] == ["Red Banarasi Silk Saree", BLUE_SAREE["name"]]
    assert all({"name", "price", "base_image_url"} <= o.keys() for o in body["product_options"])


def test_a_posted_listing_comes_back_with_the_broadcast_and_its_own_voice_note(api_client, sakhi):
    PENDING_LISTINGS[_pending_key(SESSION_A, "reseller")] = {
        "matched_product_name": GREEN_SUIT["name"], "selling_price": 1150, "cost": 700,
        "base_image_url": GREEN_SUIT["base_image_url"], "whatsapp_caption_tts": "ग्रीन सूट 1150 रुपये",
        "listing_payload": {"product_id": GREEN_SUIT["product_id"], "product_name": GREEN_SUIT["name"],
                            "category": "suits", "selling_price_inr": 1150, "cost_price_inr": 700,
                            "whatsapp_caption": "Green suit ₹1150"},
        "matched_product": GREEN_SUIT,
    }
    sakhi.classifiers.approval = "approve"

    body = send(api_client, "haan post kar do", mode="reseller").json()

    assert body["listing_finalized"] is True
    assert body["broadcast_caption"] == "Green suit ₹1150"
    assert heard(body["broadcast_audio"]) == "audio:ग्रीन सूट 1150 रुपये"
    assert (body["listing_product_name"], body["listing_category"]) == (GREEN_SUIT["name"], "suits")
    assert body["price"] == 1150


def test_a_confirmed_purchase_comes_back_with_the_order_for_the_resellers_bell(api_client, sakhi):
    LAST_VIEWED_PRODUCT[_pending_key(SESSION_A, "customer")] = BLUE_SAREE
    customer_reply(sakhi, purchase_intent_detected=True)

    body = send(api_client, "isko order kar do").json()

    [order] = sakhi.db.orders
    assert body["purchase_intent_detected"] is True
    assert body["order_id"] == order["id"]
    assert (body["confirmed_product_name"], body["confirmed_product_price"]) == (BLUE_SAREE["name"], 549)
    assert body["confirmed_product_is_unlisted"] is True


def test_when_voice_synthesis_fails_the_frontend_is_told_to_speak_it_itself(api_client, sakhi, monkeypatch):
    async def no_voice(text):
        return b""
    monkeypatch.setattr("backend.api.chat_router.synthesize_speech", no_voice)
    customer_reply(sakhi)

    body = send(api_client, "namaste").json()

    assert (body["audio"], body["voice_fallback"]) == (None, True)


# ── what the turn is given ───────────────────────────────────────────

def test_a_voice_note_is_answered_as_what_was_heard(api_client, sakhi, voice):
    voice.heard = PINK_KURTI["name"]
    customer_reply(sakhi, answered_from_product_context=True)

    body = api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A, "active_mode": "customer"},
                           files={"audio_file": ("note.webm", io.BytesIO(b"opus"), "audio/webm")}).json()

    assert body["image_url"] == PINK_KURTI["base_image_url"]   # the transcript found the kurti
    assert f"<user_message>\n{PINK_KURTI['name']}\n</user_message>" in sakhi.gemini.last_prompt(CustomerAgentResponse)


def test_unsent_fields_take_the_demo_defaults(api_client, sakhi):
    sakhi.gemini.will_return(IntentRouter, route_to="GENERAL")

    api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A, "text_message": "namaste"})

    assert "Reseller's message" in sakhi.gemini.last_prompt(IntentRouter)   # mode defaults to reseller
    assert sakhi.db.turns[0]["reseller_id"] == sakhi.db.RESELLER["id"]       # number defaults to the demo reseller


# ── failures ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["", "   "])
def test_an_empty_message_is_rejected_not_answered(api_client, sakhi, text):
    response = send(api_client, text)

    assert response.status_code == 422
    assert sakhi.db.turns == []


def test_a_voice_note_with_no_recognisable_speech_is_rejected(api_client, sakhi, voice):
    voice.heard = ""

    response = api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A},
                               files={"audio_file": ("note.webm", io.BytesIO(b"hiss"), "audio/webm")})

    assert response.status_code == 422
    assert "speech" in response.json()["detail"]


def test_a_failed_transcription_is_a_500_that_says_so(api_client, monkeypatch):
    async def broken(path):
        raise RuntimeError("ASR down")
    monkeypatch.setattr("backend.api.chat_router.transcribe_audio", broken)

    response = api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A},
                               files={"audio_file": ("note.webm", io.BytesIO(b"a"), "audio/webm")})

    assert response.status_code == 500
    assert "Voice note transcoding or transcription failed" in response.json()["detail"]


def test_a_database_outage_is_a_503_asking_to_retry(api_client, sakhi):
    sakhi.db.fail("get_or_create_reseller")

    response = send(api_client, "namaste")

    assert response.status_code == 503
    assert "try again" in response.json()["detail"]


def test_an_unexpected_error_is_a_500_that_reveals_nothing(api_client, sakhi, monkeypatch):
    def leaky(*_):
        raise RuntimeError('relation "orders" does not exist at /app/backend/db/supabase_client.py')
    monkeypatch.setattr("backend.db.supabase_client.db_client.get_or_create_reseller", leaky)

    response = send(api_client, "namaste")

    assert response.status_code == 500
    assert "orders" not in response.text and "supabase_client" not in response.text


@pytest.mark.parametrize("session_id", [
    None,                                     # an old client that never sends one
    "",
    "whatsapp:+919876543210",                 # what the old frontend keyed conversations on
    "5F0C6A3E-9D1B-4C2A-8E7F-1A2B3C4D5E6F",   # crypto.randomUUID() is lower-case
    "5f0c6a3e-9d1b-1c2a-8e7f-1a2b3c4d5e6f",   # v1: time-based, guessable
    "5f0c6a3e-9d1b-4c2a-8e7f-1a2b3c4d5e6f-x", # valid prefix, trailing junk
])
def test_a_message_without_a_valid_session_is_refused(api_client, sakhi, session_id):
    data = {"text_message": "hello"}
    if session_id is not None:
        data["session_id"] = session_id

    assert api_client.post("/api/v1/chat/send", data=data).status_code == 422
    assert sakhi.db.turns == []
