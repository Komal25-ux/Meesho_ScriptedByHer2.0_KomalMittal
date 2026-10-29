"""BodySizeLimit, driven directly at the ASGI level so the limit and the two
ways a body can arrive (with a declared length, or chunked) are explicit."""
import asyncio

import pytest

from backend.api.limits import BodySizeLimit

LIMIT = 1000
REFUSAL = [
    {"type": "http.response.start", "status": 413,
     "headers": [(b"content-type", b"application/json"), (b"content-length", b"36")]},
    {"type": "http.response.body", "body": b'{"detail":"Request body too large."}'},
]


def run(app, chunks, headers=(), scope_type="http"):
    """Sends `chunks` through the middleware into `app`; returns what the
    client received and what the app read."""
    sent, read = [], bytearray()
    messages = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        message = messages.pop(0)
        return message

    async def send(message):
        sent.append(message)

    async def recording_receive_app(scope, receive, send):
        await app(scope, receive, send, read)

    scope = {"type": scope_type, "headers": list(headers)}
    asyncio.run(BodySizeLimit(recording_receive_app, max_bytes=LIMIT)(scope, receive, send))
    return sent, bytes(read)


async def reads_all_then_answers_ok(scope, receive, send, read):
    while True:
        message = await receive()
        read.extend(message.get("body", b""))
        if not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def status_of(sent):
    return sent[0]["status"]


@pytest.mark.parametrize("size, status", [(LIMIT - 1, 200), (LIMIT, 200), (LIMIT + 1, 413)])
def test_the_limit_with_a_declared_length(size, status):
    sent, _ = run(reads_all_then_answers_ok, [b"x" * size], headers=[(b"content-length", str(size).encode())])
    assert status_of(sent) == status


def test_a_body_within_the_limit_passes_through_untouched():
    sent, read = run(reads_all_then_answers_ok, [b"a" * 400, b"b" * 400])

    assert read == b"a" * 400 + b"b" * 400
    assert sent == [{"type": "http.response.start", "status": 200, "headers": []},
                    {"type": "http.response.body", "body": b"ok"}]


def test_the_refusal_is_a_complete_json_response():
    sent, _ = run(reads_all_then_answers_ok, [b"x"], headers=[(b"content-length", b"50000000")])
    assert sent == REFUSAL


def test_an_oversized_declared_body_is_refused_before_any_of_it_is_read():
    _, read = run(reads_all_then_answers_ok, [b"x" * 10], headers=[(b"content-length", b"50000000")])
    assert read == b""


def test_a_chunked_body_is_cut_off_at_the_chunk_that_crosses_the_limit():
    sent, read = run(reads_all_then_answers_ok, [b"x" * 600, b"x" * 600, b"x" * 600])

    assert sent == REFUSAL
    assert len(read) == 600


def test_when_the_framework_answers_the_read_error_itself_the_client_still_gets_one_413():
    async def answers_400_on_a_read_error(scope, receive, send, read):
        try:
            while (await receive()).get("more_body"):
                pass
        except Exception:
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"There was an error parsing the body"})

    sent, _ = run(answers_400_on_a_read_error, [b"x" * 600, b"x" * 600])

    assert sent == REFUSAL


def test_once_a_response_has_started_an_oversized_remainder_cannot_start_another():
    async def answers_then_reads(scope, receive, send, read):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while (await receive()).get("more_body"):
            pass

    sent, _ = run(answers_then_reads, [b"x" * 600, b"x" * 600])

    assert [m["type"] for m in sent] == ["http.response.start"]
    assert status_of(sent) == 200


@pytest.mark.parametrize("scope_type", ["websocket", "lifespan"])
def test_other_connection_types_pass_straight_through(scope_type):
    seen = {}

    async def app(scope, receive, send, read):
        seen.update(scope=scope, receive=receive, send=send)

    async def receive():
        return {}

    async def send(message):
        pass

    scope = {"type": scope_type, "headers": [(b"content-length", b"50000000")]}
    asyncio.run(BodySizeLimit(lambda s, r, se: app(s, r, se, None), max_bytes=LIMIT)(scope, receive, send))

    assert seen == {"scope": scope, "receive": receive, "send": send}
