import os
import subprocess
import logging
import httpx
import google.generativeai as genai
from backend.config import settings

logger = logging.getLogger("sakhi-backend")

async def convert_to_wav(input_file_path: str) -> str:
    """
    Transcode browser recorded audio (WebM/MP4) into 16kHz, mono, PCM 16-bit WAV file.
    Uses ffmpeg CLI.
    """
    output_file_path = input_file_path.rsplit(".", 1)[0] + "_processed.wav"
    try:
        # Command to convert input file to 16kHz, mono, wav format
        cmd = [
            "ffmpeg", "-y",
            "-i", input_file_path,
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            output_file_path
        ]
        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        # Run process synchronously
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        logger.info("Audio conversion completed successfully.")
        return output_file_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg process error: {e.stderr.decode('utf-8', errors='ignore')}")
        raise e
    except Exception as e:
        logger.error(f"Failed to transcode audio: {e}")
        raise e

async def transcribe_audio(file_path: str) -> str:
    """
    Speech-to-Text conversion:
    1. Primary: Sarvam Saarika ASR API.
    2. Fallback: Google Gemini 2.5 Flash native audio transcription.
    """
    # Try Sarvam Saarika
    if settings.SARVAM_API_KEY and "YOUR_SARVAM" not in settings.SARVAM_API_KEY:
        try:
            logger.info("Transcribing audio using Sarvam Saarika ASR API...")
            async with httpx.AsyncClient() as client:
                with open(file_path, "rb") as audio_file:
                    files = {"file": ("audio.wav", audio_file, "audio/wav")}
                    headers = {"api-subscription-key": settings.SARVAM_API_KEY}
                    data = {
                        "model": "saarika:v1",
                        "language_code": "hi-IN"
                    }
                    response = await client.post(
                        "https://api.sarvam.ai/speech-to-text",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        transcription = response.json().get("transcript", "")
                        logger.info(f"Sarvam ASR Success: {transcription}")
                        if transcription:
                            return transcription
                    else:
                        logger.warning(f"Sarvam ASR returned error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Sarvam ASR API exception: {e}")

    # Fallback: Google Gemini 2.5 Flash
    if settings.GEMINI_API_KEY and "YOUR_GEMINI" not in settings.GEMINI_API_KEY:
        try:
            logger.info("ASR Fallback: Transcribing audio with Google Gemini 2.5 Flash...")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            with open(file_path, "rb") as audio_file:
                audio_bytes = audio_file.read()

            model = genai.GenerativeModel(settings.GEMINI_MODEL)
            prompt = (
                "You are an ASR system. Listen to this audio recording of an Indian reseller. "
                "Transcribe exactly what they say in Hindi, outputting standard text. Do not summarize or reply. "
                "If they speak Hindi words in English letters (Hinglish), transcribe it in natural Hindi script (Devanagari) or Hinglish as they spoke it."
            )
            
            response = model.generate_content([
                prompt,
                {"mime_type": "audio/wav", "data": audio_bytes}
            ])
            
            transcription = response.text.strip()
            logger.info(f"Gemini ASR Success: {transcription}")
            return transcription
        except Exception as e:
            logger.error(f"Gemini ASR transcription failed: {e}")
            
    logger.warning("No ASR methods succeeded. Returning empty transcription.")
    return ""

async def synthesize_speech(text: str) -> bytes:
    """
    Text-to-Speech conversion:
    1. Primary: Sarvam Bulbul TTS API (returns audio bytes).
    2. Fallback: Returns empty bytes (handled in router by returning voice_fallback: true).
    """
    if settings.SARVAM_API_KEY and "YOUR_SARVAM" not in settings.SARVAM_API_KEY:
        try:
            logger.info("Synthesizing speech using Sarvam Bulbul TTS API...")
            async with httpx.AsyncClient() as client:
                headers = {
                    "api-subscription-key": settings.SARVAM_API_KEY,
                    "Content-Type": "application/json"
                }
                payload = {
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": "meera",
                    "model": "bulbul:v1",
                    "pitch": 0,
                    "pace": 1.00,
                    "loudness": 1.5,
                    "enable_preprocessing": True
                }
                response = await client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info("Sarvam TTS Success.")
                    # Sarvam API returns JSON base64 encoded audio or raw bytes depending on endpoints.
                    # Standard Bulbul POST returns JSON containing base64 string under audios list.
                    data = response.json()
                    audios = data.get("audios", [])
                    if audios:
                        import base64
                        audio_b64 = audios[0]
                        return base64.b64decode(audio_b64)
                else:
                    logger.warning(f"Sarvam TTS returned error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Sarvam TTS API exception: {e}")

    logger.info("Sarvam TTS not available or failed. Falling back to browser-native TTS.")
    return b""
