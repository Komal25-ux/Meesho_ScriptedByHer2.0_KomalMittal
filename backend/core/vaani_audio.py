import os
import re
import subprocess
import logging
import httpx
from typing import Optional
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
    # Keep the digit group's own commas (Sarvam reads "54,090" as a whole
    # number naturally; stripping them here would leave raw "54090" digits,
    # which Sarvam reads one-by-one instead - see prompt_growth_agent.md).
    text = _RUPEE_PATTERN.sub(lambda m: f"{m.group(1)} \u0930\u0941\u092A\u092F\u0947", text)
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

_SARVAM_KEY_INDEX = 0

def get_sarvam_api_key() -> Optional[str]:
    global _SARVAM_KEY_INDEX
    keys = [k for k in [settings.SARVAM_API_KEY, settings.SARVAM_API_KEY_FALLBACK] if k and "YOUR_SARVAM" not in k]
    if not keys:
        return None
    return keys[_SARVAM_KEY_INDEX % len(keys)]

def rotate_sarvam_key():
    global _SARVAM_KEY_INDEX
    keys = [k for k in [settings.SARVAM_API_KEY, settings.SARVAM_API_KEY_FALLBACK] if k and "YOUR_SARVAM" not in k]
    if keys:
        _SARVAM_KEY_INDEX = (_SARVAM_KEY_INDEX + 1) % len(keys)
        logger.info(f"Rotating Sarvam API Key index to: {_SARVAM_KEY_INDEX}")

async def transcribe_audio(file_path: str) -> str:
    """
    Speech-to-Text conversion:
    1. Primary: Sarvam Saarika ASR API (with API key rotation on exhaustion/errors).
    2. Fallback: Google Gemini 2.5 Flash native audio transcription.
    """
    keys = [k for k in [settings.SARVAM_API_KEY, settings.SARVAM_API_KEY_FALLBACK] if k and "YOUR_SARVAM" not in k]
    num_keys = len(keys) if keys else 0

    if num_keys > 0:
        for attempt in range(num_keys):
            active_key = get_sarvam_api_key()
            if not active_key:
                break
            try:
                logger.info(f"Transcribing audio using Sarvam Saarika ASR API (Key index {_SARVAM_KEY_INDEX})...")
                async with httpx.AsyncClient() as client:
                    with open(file_path, "rb") as audio_file:
                        files = {"file": ("audio.wav", audio_file, "audio/wav")}
                        headers = {"api-subscription-key": active_key}
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
                        elif response.status_code in [401, 403, 429]:
                            logger.warning(f"Sarvam ASR key exhausted/blocked ({response.status_code}). Rotating...")
                            rotate_sarvam_key()
                            continue
                        else:
                            logger.warning(f"Sarvam ASR returned error {response.status_code}: {response.text}")
                            rotate_sarvam_key()
                            continue
            except Exception as e:
                logger.error(f"Sarvam ASR API exception: {e}. Rotating...")
                rotate_sarvam_key()
                continue

    # Fallback: Gemini multimodal audio transcription (tries a chain of models)
    logger.info("Sarvam ASR failed or unavailable. Using Gemini audio transcription fallback...")
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
    1. Primary: Sarvam Bulbul TTS API (with key rotation on exhaustion/errors).
    2. Fallback: Returns empty bytes (handled in router by returning voice_fallback: true).
    """
    keys = [k for k in [settings.SARVAM_API_KEY, settings.SARVAM_API_KEY_FALLBACK] if k and "YOUR_SARVAM" not in k]
    num_keys = len(keys) if keys else 0

    if num_keys > 0:
        for attempt in range(num_keys):
            active_key = get_sarvam_api_key()
            if not active_key:
                break
            try:
                logger.info(f"Synthesizing speech using Sarvam Bulbul TTS API (Key index {_SARVAM_KEY_INDEX})...")
                clean_text = sanitize_for_tts(text)
                tts_text = clean_text if len(clean_text) <= 500 else clean_text[:500].rsplit(" ", 1)[0]
                async with httpx.AsyncClient() as client:
                    headers = {
                        "api-subscription-key": active_key,
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "inputs": [tts_text],
                        "target_language_code": "hi-IN",
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
                        data = response.json()
                        audios = data.get("audios", [])
                        if audios:
                            import base64
                            audio_b64 = audios[0]
                            return base64.b64decode(audio_b64)
                    elif response.status_code in [401, 403, 429]:
                        logger.warning(f"Sarvam TTS key exhausted/blocked ({response.status_code}). Rotating...")
                        rotate_sarvam_key()
                        continue
                    else:
                        logger.warning(f"Sarvam TTS returned error {response.status_code}: {response.text}")
                        rotate_sarvam_key()
                        continue
            except Exception as e:
                logger.error(f"Sarvam TTS API exception: {e}. Rotating...")
                rotate_sarvam_key()
                continue

    logger.info("Sarvam TTS not available or failed. Falling back to browser-native TTS.")
    return b""
