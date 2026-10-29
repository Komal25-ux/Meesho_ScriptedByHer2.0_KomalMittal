import pytest
from starlette.websockets import WebSocketDisconnect

DEPLOYED_FRONTEND = "https://meesho-sakhi-komal25.vercel.app"
SESSION = "2c4e6a8c-0e2a-4c6e-8a0c-2e4a6c8e0a2c"


def _preflight(api_client, origin):
    return api_client.options(
        "/api/v1/chat/send",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


@pytest.mark.parametrize("origin", [DEPLOYED_FRONTEND, "http://localhost:5173"])
def test_the_frontend_origins_may_call_the_api(api_client, origin):
    response = _preflight(api_client, origin)

    assert response.headers.get("access-control-allow-origin") == origin
    # No cookies or auth headers are used, so credentials are never allowed.
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "https://meesho-sakhi-komal25.vercel.app.evil.example",  # prefix trick
    "http://meesho-sakhi-komal25.vercel.app",                # downgraded scheme
    "null",                                                  # sandboxed iframe / file://
])
def test_other_origins_are_not_allowed(api_client, origin):
    response = _preflight(api_client, origin)

    assert "access-control-allow-origin" not in response.headers


def test_trace_socket_rejects_a_page_on_another_site(api_client):
    with pytest.raises(WebSocketDisconnect):
        with api_client.websocket_connect(
            f"/ws/agent-logs?session_id={SESSION}", headers={"origin": "https://evil.example"}
        ) as ws:
            ws.receive_text()


def test_trace_socket_accepts_the_deployed_frontend(api_client):
    with api_client.websocket_connect(
        f"/ws/agent-logs?session_id={SESSION}", headers={"origin": DEPLOYED_FRONTEND}
    ) as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


# ── the agent-trace WebSocket ────────────────────────────────────────
# Trace logs carry the user's own words and phone number, so a dashboard only
# ever receives the traces of the conversation it belongs to.

OTHER_SESSION = "0d6b2f4e-1c3a-4b5d-9e7f-8a9b0c1d2e3f"


def test_a_turns_traces_reach_its_own_dashboard_and_no_other(api_client, sakhi):
    from backend.core.gemini_utils import IntentRouter
    sakhi.gemini.will_return(IntentRouter, route_to="GENERAL")

    with api_client.websocket_connect(f"/ws/agent-logs?session_id={SESSION}") as own, \
         api_client.websocket_connect(f"/ws/agent-logs?session_id={OTHER_SESSION}") as other:
        api_client.post("/api/v1/chat/send", data={"session_id": SESSION, "text_message": "namaste"})

        first = own.receive_json()
        assert (first["agent"], first["action"]) == ("Orchestrator", "Memory Retrieval")

        other.send_text("ping")
        assert other.receive_text() == "pong"   # nothing was queued ahead of the pong


@pytest.mark.parametrize("query", ["", "?session_id=", "?session_id=whatsapp:+919876543210"])
def test_a_dashboard_without_a_valid_session_is_refused(api_client, query):
    with pytest.raises(WebSocketDisconnect):
        with api_client.websocket_connect(f"/ws/agent-logs{query}") as ws:
            ws.receive_text()
