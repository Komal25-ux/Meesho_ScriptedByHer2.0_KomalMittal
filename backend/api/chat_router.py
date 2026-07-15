import os
import shutil
import base64
import logging
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from typing import Optional
from backend.core.vaani_audio import convert_to_wav, transcribe_audio, synthesize_speech
from backend.core.orchestrator import sakhi_orchestrator
from backend.api.ws_router import manager
from backend.db.supabase_client import db_client

logger = logging.getLogger("sakhi-backend")
router = APIRouter()

# Create temp uploads folder in workspace
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

@router.post("/chat/send")
async def chat_send(
    user_id: Optional[str] = Form(None),
    whatsapp_number: Optional[str] = Form("whatsapp:+919876543210"),
    text_message: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None)
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
            "reseller_name": "",
            "reseller_location": "",
            "reseller_language": "",
            "reseller_dialect": "",
            "detected_intent": "",
            "intent_confidence": 0.0,
            "reply_text": "",
            "reply_audio_b64": None,
            "reply_image_url": None,
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

        # 5. Synthesize TTS Speech (Text-to-Speech)
        tts_bytes = await synthesize_speech(reply_text)
        audio_b64 = None
        voice_fallback = True

        if tts_bytes:
            audio_b64 = base64.b64encode(tts_bytes).decode("utf-8")
            voice_fallback = False

        return {
            "text": reply_text,
            "audio": audio_b64,
            "image_url": reply_image_url,
            "voice_fallback": voice_fallback
        }

    except Exception as e:
        logger.error(f"Error in chat_send: {e}")
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
