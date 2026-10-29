"""The server keeps answering while a turn is in progress, and the two voice
notes of a posted listing are made at the same time."""
import asyncio
import threading

import httpx

from backend.tests.support.sessions import SESSION_A


def test_a_slow_turn_does_not_stop_the_server_answering_others(api_client, monkeypatch):
    from backend.main import app

    graph_running, release_graph = threading.Event(), threading.Event()

    def slow_graph(state):
        # Blocks its thread for the whole turn, like the real synchronous SDKs.
        graph_running.set()
        release_graph.wait(timeout=5)
        return {"reply_text": "done", "trace_logs": []}

    monkeypatch.setattr("backend.api.chat_router.sakhi_orchestrator.invoke", slow_graph)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            chat = asyncio.create_task(client.post("/api/v1/chat/send", data={"session_id": SESSION_A, "text_message": "hi"}))
            await asyncio.to_thread(graph_running.wait, 5)
            health = await asyncio.wait_for(client.get("/health"), timeout=2)
            still_running = not chat.done()
            release_graph.set()
            return health, still_running, await chat

    health, still_running, chat = asyncio.run(scenario())

    assert health.status_code == 200 and still_running
    assert chat.status_code == 200


def test_reply_and_broadcast_voice_notes_are_made_at_the_same_time(api_client, monkeypatch):
    in_flight, both_started = [], asyncio.Event()

    async def tts_that_waits_for_its_sibling(text):
        in_flight.append(text)
        if len(in_flight) == 2:
            both_started.set()
        # Made one after the other, the first never sees its sibling and times out.
        await asyncio.wait_for(both_started.wait(), timeout=2)
        return b"audio"

    monkeypatch.setattr("backend.api.chat_router.synthesize_speech", tts_that_waits_for_its_sibling)
    monkeypatch.setattr("backend.api.chat_router.sakhi_orchestrator.invoke", lambda state: {
        "reply_text": "Post ho gaya", "reply_tts_text": "पोस्ट हो गया",
        "listing_finalized": True, "listing_broadcast_caption_tts": "नयी साड़ी", "trace_logs": []})

    response = api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A, "text_message": "haan"})

    assert response.status_code == 200
    assert sorted(in_flight) == sorted(["पोस्ट हो गया", "नयी साड़ी"])


def test_no_broadcast_voice_note_is_made_when_nothing_was_posted(api_client, voice, monkeypatch):
    monkeypatch.setattr("backend.api.chat_router.sakhi_orchestrator.invoke",
                        lambda state: {"reply_text": "Namaste", "trace_logs": []})

    body = api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A, "text_message": "hi"}).json()

    assert voice.spoken == ["Namaste"]
    assert body["broadcast_audio"] is None
