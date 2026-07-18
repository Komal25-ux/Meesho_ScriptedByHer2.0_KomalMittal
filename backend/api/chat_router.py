import os
import time
import shutil
import base64
import logging
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from typing import Optional
from backend.core.vaani_audio import convert_to_wav, transcribe_audio, synthesize_speech
from backend.core.orchestrator import sakhi_orchestrator, run_returns_proactive_outreach
from backend.api.ws_router import manager
from backend.db.supabase_client import db_client

logger = logging.getLogger("sakhi-backend")
router = APIRouter()

# Create temp uploads folder in workspace
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

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

@router.get("/tts/greeting")
async def tts_greeting(mode: str = Query("reseller")):
    """Pre-synthesizes the mode-specific welcome message so the UI can play a real
    Sarvam voice note on load/mode-switch instead of falling back to browser TTS."""
    text = GREETING_TEXT.get(mode, GREETING_TEXT["reseller"])
    tts_text = GREETING_TTS_TEXT.get(mode, GREETING_TTS_TEXT["reseller"])
    tts_bytes = await synthesize_speech(tts_text)
    audio_b64 = base64.b64encode(tts_bytes).decode("utf-8") if tts_bytes else None
    return {"text": text, "audio": audio_b64}

@router.post("/chat/send")
async def chat_send(
    user_id: Optional[str] = Form(None),
    whatsapp_number: Optional[str] = Form("whatsapp:+919876543210"),
    text_message: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    active_mode: Optional[str] = Form("reseller")
):
    try:
        user_input = text_message
        input_type = "text"
        
        # 1. Process Voice Note if uploaded
        if audio_file:
            input_type = "voice"
            # Save uploaded webm/mp4 file locally
            temp_input_path = os.path.join(TEMP_DIR, audio_file.filename)
            logger.info(f"Saving temporary audio file to {temp_input_path}")
            
            with open(temp_input_path, "wb") as buffer:
                shutil.copyfileobj(audio_file.file, buffer)
                
            try:
                # Transcode to WAV (16kHz mono)
                logger.info("Transcoding WebM to WAV...")
                wav_path = await convert_to_wav(temp_input_path)
                
                # Perform speech-to-text (ASR)
                logger.info("Performing ASR transcription...")
                user_input = await transcribe_audio(wav_path)
                
                # Clean up files
                if os.path.exists(temp_input_path):
                    os.remove(temp_input_path)
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except Exception as audio_err:
                logger.error(f"Failed during audio processing pipeline: {audio_err}")
                user_input = ""
                # Clean up files if they exist
                if os.path.exists(temp_input_path):
                    os.remove(temp_input_path)
                raise HTTPException(status_code=500, detail="Voice note transcoding or transcription failed.")
                
        # 2. Safety Fallback if transcription is empty
        if not user_input:
            user_input = "hello" # Default fall-through

        logger.info(f"Received user input: {user_input} (Type: {input_type})")

        # 3. Invoke LangGraph Orchestrator
        initial_state = {
            "reseller_id": "",
            "whatsapp_number": whatsapp_number,
            "raw_input": user_input,
            "input_type": input_type,
            "active_mode": active_mode or "reseller",
            "reseller_name": "",
            "reseller_location": "",
            "reseller_language": "",
            "reseller_dialect": "",
            "detected_intent": "",
            "intent_confidence": 0.0,
            "pending_route": "",
            "pending_return_route": "",
            "pending_selection_route": "",
            "reply_text": "",
            "reply_audio_b64": None,
            "reply_image_url": None,
            "reply_price": None,
            "reply_product_options": None,
            "reply_tts_text": None,
            "listing_finalized": False,
            "listing_broadcast_caption": None,
            "listing_broadcast_caption_tts": None,
            "reply_purchase_intent_detected": False,
            "reply_confirmed_product_name": None,
            "reply_confirmed_product_price": None,
            "reply_handoff_triggered": False,
            "trace_logs": [],
            "context_data": None
        }

        logger.info("Invoking LangGraph multi-agent orchestrator...")
        # Invoke LangGraph state machine synchronously
        result = sakhi_orchestrator.invoke(initial_state)

        # 4. Stream trace logs to WebSocket Dashboard clients
        logger.info("Streaming agent trace logs via WebSocket...")
        for trace_log in result.get("trace_logs", []):
            await manager.broadcast(trace_log)

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
        tts_bytes = await synthesize_speech(tts_input_text)
        audio_b64 = None
        voice_fallback = True

        if tts_bytes:
            audio_b64 = base64.b64encode(tts_bytes).decode("utf-8")
            voice_fallback = False

        # 6. If a catalog listing was just finalized, synthesize a SEPARATE
        # voice note for the broadcast that lands in the Customer segment - it
        # reads the promotional caption, not the reseller's own confirmation
        # reply, so it needs its own TTS pass over listing_broadcast_caption_tts.
        broadcast_audio_b64 = None
        if result.get("listing_finalized"):
            broadcast_tts_text = result.get("listing_broadcast_caption_tts") or result.get("listing_broadcast_caption")
            if broadcast_tts_text:
                broadcast_tts_bytes = await synthesize_speech(broadcast_tts_text)
                if broadcast_tts_bytes:
                    broadcast_audio_b64 = base64.b64encode(broadcast_tts_bytes).decode("utf-8")

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
            "purchase_intent_detected": bool(result.get("reply_purchase_intent_detected")),
            "confirmed_product_name": result.get("reply_confirmed_product_name"),
            "confirmed_product_price": result.get("reply_confirmed_product_price"),
            "handoff_triggered": bool(result.get("reply_handoff_triggered"))
        }

    except Exception as e:
        logger.error(f"Error in chat_send: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/system/trigger-return")
async def system_trigger_return(
    whatsapp_number: Optional[str] = Form("whatsapp:+919876543210"),
    order_id: Optional[str] = Form("104"),
    product_name: Optional[str] = Form("Red Cotton Kurti")
):
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
        outreach = run_returns_proactive_outreach(
            whatsapp_number or "whatsapp:+919876543210", order_id or "104", product_name or "Red Cotton Kurti"
        )

        db_client.save_return({
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
        await manager.broadcast(trace_log)

        tts_bytes = await synthesize_speech(outreach["reply_tts_text"])
        audio_b64 = base64.b64encode(tts_bytes).decode("utf-8") if tts_bytes else None

        return {
            "text": outreach["reply_text"],
            "audio": audio_b64,
            "image_url": outreach["reply_image_url"],
            "voice_fallback": not bool(audio_b64)
        }
    except Exception as e:
        logger.error(f"Error in system_trigger_return: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/history")
async def chat_history(whatsapp_number: str = Query("whatsapp:+919876543210"), limit: int = 10):
    try:
        # Load reseller ID
        reseller = db_client.get_or_create_reseller(whatsapp_number)
        history = db_client.get_conversation_history(reseller["id"], limit=limit)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error fetching conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
