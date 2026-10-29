"""Abuse limits at the API: rate, body size and field shapes."""
from unittest.mock import patch

import pytest

from backend.api import limits
from backend.core.prompt_safety import MAX_PROMPT_TEXT_CHARS

from backend.tests.support.sessions import SESSION_A, SESSION_B

OK_TURN = {"reply_text": "ok", "trace_logs": []}


@pytest.fixture
def graph_ok():
    with patch("backend.api.chat_router.sakhi_orchestrator.invoke", return_value=OK_TURN) as invoke:
        yield invoke


def send(api_client, session=SESSION_A, **fields):
    return api_client.post("/api/v1/chat/send", data={"session_id": session, "text_message": "hi", **fields})


# ── rate ─────────────────────────────────────────────────────────────

def test_a_session_over_its_limit_gets_429_with_a_retry_after(api_client, graph_ok, monkeypatch):
    monkeypatch.setattr(limits.session_limiter, "limit", 3)

    statuses = [send(api_client).status_code for _ in range(4)]
    refused = send(api_client)

    assert statuses == [200, 200, 200, 429]
    assert 1 <= int(refused.headers["retry-after"]) <= 60
    assert graph_ok.call_count == 3  # the refused requests never reached the model


def test_one_busy_session_does_not_block_another(api_client, graph_ok, monkeypatch):
    monkeypatch.setattr(limits.session_limiter, "limit", 1)
    send(api_client, SESSION_A)

    assert send(api_client, SESSION_A).status_code == 429
    assert send(api_client, SESSION_B).status_code == 200


def test_new_session_ids_do_not_get_round_the_per_address_limit(api_client, graph_ok, monkeypatch):
    monkeypatch.setattr(limits.ip_limiter, "limit", 2)
    sessions = [SESSION_A, SESSION_B, "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"]

    statuses = [send(api_client, s).status_code for s in sessions]

    assert statuses == [200, 200, 429]


@pytest.mark.parametrize("path, method", [
    ("/api/v1/tts/greeting?mode=reseller", "get"),
    ("/api/v1/system/trigger-return", "post"),
])
def test_every_endpoint_that_spends_quota_is_rate_limited(api_client, monkeypatch, path, method):
    monkeypatch.setattr(limits.ip_limiter, "limit", 0)

    response = getattr(api_client, method)(path, **({"data": {"session_id": SESSION_A}} if method == "post" else {}))

    assert response.status_code == 429


def test_health_is_never_rate_limited(api_client, monkeypatch):
    monkeypatch.setattr(limits.ip_limiter, "limit", 0)
    assert api_client.get("/health").status_code == 200


# ── size ─────────────────────────────────────────────────────────────

def test_an_upload_over_the_request_limit_is_refused_with_413(api_client, graph_ok):
    from backend.config import settings

    response = api_client.post(
        "/api/v1/chat/send", data={"session_id": SESSION_A},
        files={"audio_file": ("note.webm", b"x" * (settings.MAX_REQUEST_BYTES + 1), "audio/webm")},
    )

    assert response.status_code == 413
    graph_ok.assert_not_called()


# ── field shapes ─────────────────────────────────────────────────────

@pytest.mark.parametrize("length, status", [
    (MAX_PROMPT_TEXT_CHARS - 1, 200),
    (MAX_PROMPT_TEXT_CHARS, 200),
    (MAX_PROMPT_TEXT_CHARS + 1, 422),
])
def test_message_length_limit(api_client, graph_ok, length, status):
    assert send(api_client, text_message="a" * length).status_code == status


@pytest.mark.parametrize("number, status", [
    ("whatsapp:+919876543210", 200),
    ("whatsapp:+12345678", 200),       # 8 digits, the shortest allowed
    ("whatsapp:+1234567", 422),
    ("+919876543210", 422),
    ("whatsapp:+91 98765 43210", 422),
])
def test_whatsapp_number_shape(api_client, graph_ok, number, status):
    assert send(api_client, whatsapp_number=number).status_code == status


@pytest.mark.parametrize("mode, status", [("reseller", 200), ("customer", 200), ("admin", 422), ("Customer", 422)])
def test_mode_must_be_reseller_or_customer(api_client, graph_ok, mode, status):
    assert send(api_client, active_mode=mode).status_code == status


def test_an_empty_form_field_counts_as_not_sent_so_the_default_applies(api_client, graph_ok):
    send(api_client, active_mode="")

    assert graph_ok.call_args[0][0]["active_mode"] == "reseller"


@pytest.mark.parametrize("fields", [
    {"order_id": "104; DROP TABLE"},
    {"order_id": "x" * 21},
    {"product_name": "p" * 81},
])
def test_the_return_trigger_only_accepts_demo_shaped_fields(api_client, fields):
    with patch("backend.api.chat_router.run_returns_proactive_outreach") as outreach:
        response = api_client.post("/api/v1/system/trigger-return", data={"session_id": SESSION_A, **fields})

    assert response.status_code == 422
    outreach.assert_not_called()


@pytest.mark.parametrize("message_id, status", [
    ("0d4f6a8c-1e3a-4c5e-9a7c-2e4f6a8c0e1a", 200),
    ("not-a-uuid", 422),
    ("0D4F6A8C-1E3A-4C5E-9A7C-2E4F6A8C0E1A", 422),
])
def test_message_id_must_be_a_v4_uuid(api_client, graph_ok, message_id, status):
    assert send(api_client, client_message_id=message_id).status_code == status


def test_the_message_id_reaches_the_turn(api_client, graph_ok):
    send(api_client, client_message_id="0d4f6a8c-1e3a-4c5e-9a7c-2e4f6a8c0e1a")

    assert graph_ok.call_args[0][0]["client_message_id"] == "0d4f6a8c-1e3a-4c5e-9a7c-2e4f6a8c0e1a"


# ── timing ───────────────────────────────────────────────────────────

def test_a_typed_turn_reports_graph_tts_and_total_timing(api_client, graph_ok):
    from scripts.measure_latency import parse_server_timing

    stages = parse_server_timing(send(api_client).headers["server-timing"])

    assert set(stages) == {"graph", "tts", "total"}
    assert stages["total"] >= stages["graph"]


def test_a_voice_turn_also_reports_speech_to_text_timing(api_client, graph_ok):
    import io
    from scripts.measure_latency import parse_server_timing

    response = api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A},
                               files={"audio_file": ("note.webm", io.BytesIO(b"a"), "audio/webm")})

    assert "asr" in parse_server_timing(response.headers["server-timing"])


def test_the_browser_may_read_the_timing_header_cross_origin(api_client, graph_ok):
    response = api_client.post(
        "/api/v1/chat/send", data={"session_id": SESSION_A, "text_message": "hi"},
        headers={"Origin": "https://meesho-sakhi-komal25.vercel.app"},
    )

    assert "server-timing" in response.headers["access-control-expose-headers"].lower()
