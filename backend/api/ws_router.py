from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
import json
import logging
from typing import Dict, List

from backend.config import settings

logger = logging.getLogger("sakhi-backend")
router = APIRouter()

# A browser tab's conversation id (crypto.randomUUID() in the frontend). It is
# the only thing tying a trace stream to a chat, so it has to be unguessable -
# anything that isn't a v4-shaped uuid is rejected before it reaches a handler.
SESSION_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


class ConnectionManager:
    """Trace logs carry the user's own messages and phone number, so each one
    is delivered only to the sockets of the session that produced it - never
    to every open dashboard."""

    def __init__(self):
        self.sessions: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.sessions.setdefault(session_id, []).append(websocket)
        logger.info(f"WebSocket connected. Open sessions: {len(self.sessions)}")

    def disconnect(self, session_id: str, websocket: WebSocket):
        sockets = self.sessions.get(session_id, [])
        if websocket in sockets:
            sockets.remove(websocket)
        if not sockets:
            self.sessions.pop(session_id, None)
        logger.info(f"WebSocket disconnected. Open sessions: {len(self.sessions)}")

    async def broadcast(self, session_id: str, message: dict):
        message_str = json.dumps(message)
        for connection in list(self.sessions.get(session_id, [])):
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Failed to send websocket trace to connection: {e}")
                # The read loop below notices the dead socket and disconnects it.

manager = ConnectionManager()

@router.websocket("/ws/agent-logs")
async def websocket_endpoint(websocket: WebSocket, session_id: str = Query(..., pattern=SESSION_ID_PATTERN)):
    # CORS does not apply to WebSockets, so the browser origin is checked
    # here. Browsers always send Origin; a non-browser client can omit or
    # fake it, so this stops other websites, not scripts.
    origin = websocket.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in settings.allowed_origins:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(session_id, websocket)
    try:
        # Keep connection open and respond to simple messages/pings
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket exception: {e}")
        manager.disconnect(session_id, websocket)
