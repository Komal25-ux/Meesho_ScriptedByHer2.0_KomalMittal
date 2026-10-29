"""Request limits: how often, and how big.

Every message costs Gemini and Sarvam quota, so without these anyone could
script requests and spend it all, or upload a file large enough to fill the
server's disk.

The rate limits live in this process's memory. With several instances each
one counts on its own, so the effective limit is N times the setting; a
shared counter (Redis, or a Postgres table) would be the next step if
Sakhi ever runs on more than one.
"""
import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional

from fastapi import HTTPException, Request

from backend.config import settings

__all__ = ["SlidingWindowLimiter", "BodySizeLimit", "ip_limiter", "session_limiter", "limit_by_ip", "limit_by_session"]


class SlidingWindowLimiter:
    """At most `limit` hits per key in any `window_seconds` span."""

    # Past this many tracked keys, keys with no hit inside the window are
    # dropped, so a flood of one-off addresses can't grow memory without end.
    MAX_TRACKED_KEYS = 10_000

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> Optional[float]:
        """Records a hit and returns None if it is allowed. If the key is over
        its limit, records nothing and returns how many seconds until the
        oldest hit leaves the window."""
        if self.limit <= 0:
            return self.window  # a limit of zero admits nothing
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - now
            hits.append(now)
            if len(self._hits) > self.MAX_TRACKED_KEYS:
                self._forget_idle(now)
            return None

    def _forget_idle(self, now: float) -> None:
        idle = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window]
        for key in idle:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


ip_limiter = SlidingWindowLimiter(settings.RATE_LIMIT_IP_PER_MINUTE, 60)
session_limiter = SlidingWindowLimiter(settings.RATE_LIMIT_SESSION_PER_MINUTE, 60)


def _enforce(limiter: SlidingWindowLimiter, key: str) -> None:
    wait = limiter.hit(key)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again.",
            headers={"Retry-After": str(max(1, math.ceil(wait)))},
        )


def limit_by_ip(request: Request) -> None:
    """FastAPI dependency for every endpoint that spends model or voice quota.
    Behind Render's proxy the client address comes from X-Forwarded-For,
    which uvicorn applies when started with --proxy-headers (see Dockerfile)."""
    _enforce(ip_limiter, f"ip:{request.client.host if request.client else 'unknown'}")


def limit_by_session(session_id: str) -> None:
    _enforce(session_limiter, f"session:{session_id}")


class _BodyTooLarge(Exception):
    pass


class BodySizeLimit:
    """ASGI middleware refusing request bodies over `max_bytes` with 413.

    A declared Content-Length over the limit is refused before anything is
    read. A body without one (chunked) is counted as it streams in and cut
    off at the limit, so an oversized upload never reaches disk in full."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            return await self._refuse(send)

        received = 0
        too_large = False
        response_started = False

        async def counting_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message):
            nonlocal response_started
            # The framework may catch the read error and answer 400 itself;
            # whatever it answers, an oversized body gets 413.
            if too_large:
                if not response_started:
                    response_started = True
                    await self._refuse(send)
                return
            response_started = response_started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _BodyTooLarge:
            if not response_started:
                await self._refuse(send)

    @staticmethod
    async def _refuse(send):
        body = b'{"detail":"Request body too large."}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
