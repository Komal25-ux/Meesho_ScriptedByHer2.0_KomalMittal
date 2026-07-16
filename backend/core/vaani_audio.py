import os
import re
import subprocess
import logging
import httpx
from backend.config import settings
from backend.core.gemini_utils import generate_with_fallback

logger = logging.getLogger("sakhi-backend")

# Sarvam Bulbul TTS mispronounces/garbles emoji glyphs and tries to read markdown
# formatting characters aloud, and reads "\u20B9" unreliably. Rather than blacklist
# each offending category separately, whitelist what's actually safe to speak:
# Latin alphanumerics, the Devanagari block (incl. its own punctuation, danda
# "\u0964" and double-danda "\u0965"), spaces, and basic sentence punctuation. Currency
# is normalized to spoken words first, since "\u20B9" itself falls outside the
# whitelist and would otherwise just vanish instead of being read as "rupaye".
_RUPEE_PATTERN = re.compile(r"\u20B9\s?(\d[\d,]*)")
_TTS_WHITELIST_PATTERN = re.compile(r"[^a-zA-Z0-9\u0900-\u097F\u0964\u0965 ,.?!]")

def sanitize_for_tts(text: str) -> str:
    text = _RUPEE_PATTERN.sub(lambda m: f"{m.group(1).replace(',', '')} \u0930\u0941\u092A\u092F\u0947", text)
    text = _TTS_WHITELIST_PATTERN.sub(" ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()

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
                        "model": "saarika:v2.5",
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

    # Fallback: Gemini multimodal audio transcription (tries a chain of models)
    with open(file_path, "rb") as audio_file:
        audio_bytes = audio_file.read()

    prompt = (
        "You are an ASR system. Listen to this audio recording of an Indian reseller. "
        "Transcribe exactly what they say in Hindi, outputting standard text. Do not summarize or reply. "
        "If they speak Hindi words in English letters (Hinglish), transcribe it in natural Hindi script (Devanagari) or Hinglish as they spoke it."
    )
    transcription = generate_with_fallback([prompt, {"mime_type": "audio/wav", "data": audio_bytes}])
    if transcription:
        logger.info(f"Gemini ASR Success: {transcription}")
        return transcription

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
            # Sanitize for the voice payload only - the chat UI still shows the
            # original text with emojis/markdown/₹ intact. Applied here (not at
            # each call site) so it's a deterministic safety net regardless of
            # which Gemini fallback model produced the text or how well it
            # followed the phonetic prompt rules.
            clean_text = sanitize_for_tts(text)
            # Sarvam Bulbul TTS rejects inputs over 500 characters; the Catalog agent's
            # replies (Didi text + WhatsApp caption) regularly exceed this, so clip at a
            # word boundary for the voice note while the full text still shows in chat.
            tts_text = clean_text if len(clean_text) <= 500 else clean_text[:500].rsplit(" ", 1)[0]
            async with httpx.AsyncClient() as client:
                headers = {
                    "api-subscription-key": settings.SARVAM_API_KEY,
                    "Content-Type": "application/json"
                }
                payload = {
                    "inputs": [tts_text],
                    "target_language_code": "hi-IN",
                    # Reverted to "anushka" - the "manisha" swap sounded worse in practice.
                    # Natural pace (1.0) and the highest sample rate Sarvam accepts for
                    # bulbul:v2 (24kHz) for clean, artifact-free playback.
                    "speaker": "anushka",
                    "model": "bulbul:v2",
                    "pitch": 0,
                    "pace": 1.0,
                    "loudness": 1.5,
                    "enable_preprocessing": True,
                    "speech_sample_rate": 24000
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
