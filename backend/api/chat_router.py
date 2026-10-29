import os
import time
import uuid
import shutil
import asyncio
import base64
import logging
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from backend.core.vaani_audio import convert_to_wav, transcribe_audio, synthesize_speech
from backend.core.orchestrator import sakhi_orchestrator, run_returns_proactive_outreach
from backend.api.ws_router import manager, SESSION_ID_PATTERN
from backend.db.supabase_client import db_client
from backend.core.session import session_turn
from backend.core.state import new_turn_state
from backend.errors import DependencyUnavailable
from backend.api.limits import limit_by_ip, limit_by_session
from backend.api.timing import StageTimer
from backend.core.prompt_safety import MAX_PROMPT_TEXT_CHARS

logger = logging.getLogger("sakhi-backend")
router = APIRouter()

# Create temp uploads folder in workspace
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

# Error bodies stay generic: exception text can carry SQL, file paths or
# provider responses. The detail is in the server log.
_RETRY_LATER = "A service Sakhi depends on is unavailable right now. Please try again in a moment."
_INTERNAL_ERROR = "Something went wrong on our side."

_ALLOWED_AUDIO_SUFFIXES = {".webm", ".mp4", ".m4a", ".ogg", ".wav"}


async def _no_audio() -> bytes:
    return b""


def _temp_upload_path(client_filename: Optional[str]) -> str:
    """Server-chosen path for an uploaded voice note. The client's filename is
    never used as a path: it can contain "../" or be absolute, which would let
    a request write (and, on cleanup, delete) files outside TEMP_DIR. It also
    isn't unique - the frontend names every recording "reseller_recording.webm",
    so two voice notes arriving together would overwrite each other. Only a
    known audio extension is kept, as a hint for ffmpeg."""
    suffix = os.path.splitext(client_filename or "")[1].lower()
    if suffix not in _ALLOWED_AUDIO_SUFFIXES:
        suffix = ".webm"
    return os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}{suffix}")

GREETING_TEXT = {
    "reseller": "Namaste Sunita didi! Main aapki AI Sakhi hu. Bolkar ya likhkar mujhse apne catalog, orders aur returns ki baatein kijiye. 🌸",
    "customer": "Namaste! Main Sakhi hu. Aap apne order, delivery, ya return ke baare mein pooch sakte hain. 🌸"
}
# Devanagari versions used only for TTS - Sarvam pronounces pure Devanagari far
# more naturally than romanized Hindi (same reasoning as the dual-output agents).
GREETING_TTS_TEXT = {
    "reseller": "नमस्ते सुनीता दीदी! मैं आपकी ए आई सखी हूँ। बोलकर या लिखकर मुझसे अपने कैटलॉग, ऑर्डर्स और रिटर्न्स की बातें कीजिये।",
    "customer": "नमस्ते! मैं सखी हूँ। आप अपने ऑर्डर, डिलीवरी, या रिटर्न के बारे में पूछ सकते हैं।"
}

WHATSAPP_NUMBER_PATTERN = r"^whatsapp:\+\d{8,15}$"
MODE_PATTERN = r"^(reseller|customer)$"


@router.get("/tts/greeting", dependencies=[Depends(limit_by_ip)])
async def tts_greeting(mode: str = Query("reseller")):
    """Pre-synthesizes the mode-specific welcome message so the UI can play a real
    Sarvam voice note on load/mode-switch instead of falling back to browser TTS."""
    text = GREETING_TEXT.get(mode, GREETING_TEXT["reseller"])
    tts_text = GREETING_TTS_TEXT.get(mode, GREETING_TTS_TEXT["reseller"])
    tts_bytes = await synthesize_speech(tts_text)
    audio_b64 = base64.b64encode(tts_bytes).decode("utf-8") if tts_bytes else None
    return {"text": text, "audio": audio_b64}

@router.post("/chat/send", dependencies=[Depends(limit_by_ip)])
async def chat_send(
    response: Response,
    session_id: str = Form(..., pattern=SESSION_ID_PATTERN),
    whatsapp_number: str = Form("whatsapp:+919876543210", pattern=WHATSAPP_NUMBER_PATTERN),
    text_message: Optional[str] = Form(None, max_length=MAX_PROMPT_TEXT_CHARS),
    audio_file: Optional[UploadFile] = File(None),
    active_mode: str = Form("reseller", pattern=MODE_PATTERN),
    client_message_id: Optional[str] = Form(None, pattern=SESSION_ID_PATTERN),
):
    limit_by_session(session_id)
    timer = StageTimer()
    try:
        user_input = text_message
        input_type = "text"

        # 1. Process Voice Note if uploaded
        if audio_file:
            input_type = "voice"
            temp_input_path = _temp_upload_path(audio_file.filename)
            wav_path = None
            logger.info(f"Saving temporary audio file to {temp_input_path}")

            with open(temp_input_path, "wb") as buffer:
                shutil.copyfileobj(audio_file.file, buffer)

            try:
                with timer.stage("asr"):
                    # Transcode to WAV (16kHz mono)
                    logger.info("Transcoding WebM to WAV...")
                    wav_path = await convert_to_wav(temp_input_path)

                    # Perform speech-to-text (ASR)
                    logger.info("Performing ASR transcription...")
                    user_input = await transcribe_audio(wav_path)
            except Exception as audio_err:
                logger.error(f"Failed during audio processing pipeline: {audio_err}")
                raise HTTPException(status_code=500, detail="Voice note transcoding or transcription failed.")
            finally:
                for path in (temp_input_path, wav_path):
                    if path and os.path.exists(path):
                        os.remove(path)
                
        # 2. Nothing to answer. This used to be replaced with "hello", so a
        # voice note the ASR could not make out got a cheerful greeting back
        # instead of a request to repeat it.
        if not (user_input or "").strip():
            what = "speech in the voice note" if input_type == "voice" else "message text"
            raise HTTPException(status_code=422, detail=f"No {what} to respond to.")

        logger.info(f"Received user input: {user_input} (Type: {input_type})")

        # 3. Invoke LangGraph Orchestrator
        initial_state = new_turn_state(
            session_id, whatsapp_number, user_input, input_type=input_type, active_mode=active_mode,
            client_message_id=client_message_id,
        )

        logger.info("Invoking LangGraph multi-agent orchestrator...")
        # The graph is synchronous end to end (Gemini SDK, supabase-py) and
        # takes seconds per turn. Calling it directly here would block the
        # event loop, and with it every other request and WebSocket on this
        # worker, so it runs on the threadpool instead.
        with timer.stage("graph"), session_turn(session_id):
            result = await run_in_threadpool(sakhi_orchestrator.invoke, initial_state)

        # 4. Stream trace logs to WebSocket Dashboard clients
        logger.info("Streaming agent trace logs via WebSocket...")
        for trace_log in result.get("trace_logs", []):
            await manager.broadcast(session_id, trace_log)

        reply_text = result.get("reply_text", "Didi, technical error ke vajah se main samajh nahi payi.")
        reply_image_url = result.get("reply_image_url", None)
        reply_price = result.get("reply_price", None)
        reply_product_options = result.get("reply_product_options", None)

        # 5. Synthesize TTS Speech (Text-to-Speech)
        # Agents emit a Devanagari "tts_text" alongside the Hinglish "ui_text"
        # (reply_text) from the same LLM call - Sarvam pronounces pure Devanagari
        # far more naturally than romanized Hindi. Falls back to reply_text for
        # any node that only sets a deterministic template reply.
        tts_input_text = result.get("reply_tts_text") or reply_text

        # 6. If a catalog listing was just finalized, synthesize a SEPARATE
        # voice note for the broadcast that lands in the Customer segment - it
        # reads the promotional caption, not the reseller's own confirmation
        # reply, so it needs its own TTS pass over listing_broadcast_caption_tts.
        broadcast_tts_text = None
        if result.get("listing_finalized"):
            broadcast_tts_text = result.get("listing_broadcast_caption_tts") or result.get("listing_broadcast_caption")

        # The two voice notes don't depend on each other, so they are
        # synthesized concurrently: a finalized listing costs one TTS
        # round-trip of latency instead of two.
        with timer.stage("tts"):
            tts_bytes, broadcast_tts_bytes = await asyncio.gather(
                synthesize_speech(tts_input_text),
                synthesize_speech(broadcast_tts_text) if broadcast_tts_text else _no_audio(),
            )
        audio_b64 = base64.b64encode(tts_bytes).decode("utf-8") if tts_bytes else None
        voice_fallback = audio_b64 is None
        broadcast_audio_b64 = base64.b64encode(broadcast_tts_bytes).decode("utf-8") if broadcast_tts_bytes else None

        response.headers["Server-Timing"] = timer.header()
        logger.info(f"Turn timing ({input_type}, {active_mode}): {response.headers['Server-Timing']}")
        return {
            "text": reply_text,
            "audio": audio_b64,
            "image_url": reply_image_url,
            "price": reply_price,
            "product_options": reply_product_options,
            "voice_fallback": voice_fallback,
            "listing_finalized": bool(result.get("listing_finalized")),
            "broadcast_caption": result.get("listing_broadcast_caption"),
            "broadcast_audio": broadcast_audio_b64,
            "listing_product_name": result.get("listing_product_name"),
            "listing_category": result.get("listing_category"),
            "purchase_intent_detected": bool(result.get("reply_purchase_intent_detected")),
            "order_id": result.get("reply_order_id"),
            "confirmed_product_name": result.get("reply_confirmed_product_name"),
            "confirmed_product_price": result.get("reply_confirmed_product_price"),
            "confirmed_product_is_unlisted": bool(result.get("reply_confirmed_product_is_unlisted")),
            "handoff_triggered": bool(result.get("reply_handoff_triggered"))
        }

    except HTTPException:
        raise
    except DependencyUnavailable as e:
        logger.error(f"chat_send could not complete the turn: {e}")
        raise HTTPException(status_code=503, detail=_RETRY_LATER)
    except Exception:
        logger.exception("Unhandled error in chat_send")
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)

@router.post("/system/trigger-return", dependencies=[Depends(limit_by_ip)])
async def system_trigger_return(
    session_id: str = Form(..., pattern=SESSION_ID_PATTERN),
    # Both end up in a prompt and in session state, so they are held to the
    # shape the demo button sends.
    order_id: str = Form("104", pattern=r"^[A-Za-z0-9-]{1,20}$"),
    product_name: str = Form("Red Cotton Kurti", min_length=1, max_length=80),
):
    limit_by_session(session_id)
    """Simulates a backend system event - e.g. a return initiated in the
    reseller's Meesho seller dashboard - that should make Sakhi proactively
    reach out to the customer, without the customer having sent anything
    first. Deliberately bypasses the LangGraph intent-detection graph: there is
    no LangGraph thread/session memory in this app for a system event to be
    "injected" into (every /chat/send call invokes the graph fresh with no
    persisted history), and faking a synthetic user message to route through
    detect_intent would be a fragile way to reach a node we already know we
    want by construction."""
    try:
        with session_turn(session_id):
            outreach = await run_in_threadpool(run_returns_proactive_outreach, session_id, order_id, product_name)

        await run_in_threadpool(db_client.save_return, {
            "reason": "system_triggered_outreach",
            "resolution": "awaiting_customer_response",
            "conversation_log": {"order_id": order_id, "product_name": product_name}
        })

        trace_log = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": "ReturnsAgent",
            "action": "Proactive Return Outreach (System Triggered)",
            "latency_ms": 0,
            "data": {"order_id": order_id, "product_name": product_name}
        }
        await manager.broadcast(session_id, trace_log)

        tts_bytes = await synthesize_speech(outreach["reply_tts_text"])
        audio_b64 = base64.b64encode(tts_bytes).decode("utf-8") if tts_bytes else None

        return {
            "text": outreach["reply_text"],
            "audio": audio_b64,
            "image_url": outreach["reply_image_url"],
            "voice_fallback": not bool(audio_b64)
        }
    except DependencyUnavailable as e:
        logger.error(f"system_trigger_return could not complete: {e}")
        raise HTTPException(status_code=503, detail=_RETRY_LATER)
    except Exception:
        logger.exception("Unhandled error in system_trigger_return")
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)
