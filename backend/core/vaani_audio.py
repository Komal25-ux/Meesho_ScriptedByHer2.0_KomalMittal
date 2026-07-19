import os
import re
import subprocess
import logging
import httpx
from typing import Optional
from backend.config import settings
from backend.core.gemini_utils import generate_with_fallback

logger = logging.getLogger("sakhi-backend")

_TRANSLITERATION_MAP = {
    r"\btotal\b": "टोटल",
    r"\brevenue\b": "रेवेन्यू",
    r"\bprofit\b": "प्रॉफिट",
    r"\bsales\b": "सेल्स",
    r"\breport\b": "रिपोर्ट",
    r"\bstar\b": "स्टार",
    r"\bperformers\b": "परफॉर्मर्स",
    r"\bperformer\b": "परफॉर्मर",
    r"\bsarees\b": "साड़ियां",
    r"\bsaree\b": "साड़ी",
    r"\bkurtis\b": "कुर्तियां",
    r"\bkurti\b": "कुर्ती",
    r"\bsuits\b": "सूट",
    r"\bsuit\b": "सूट",
    r"\btops\b": "टॉप",
    r"\btop\b": "टॉप",
    r"\blehengas\b": "लहंगे",
    r"\blehenga\b": "लहंगा",
    r"\bdresses\b": "ड्रेस",
    r"\bdress\b": "ड्रेस",
    r"\bwhatsapp\b": "व्हाट्सएप",
    r"\bstatus\b": "स्टेटस",
    r"\bcombos\b": "कॉम्बो",
    r"\bcombo\b": "कॉम्बो",
    r"\bbusiness\b": "बिज़नेस",
    r"\banalysis\b": "एनालिसिस",
    r"\btips\b": "टिप्स",
    r"\btip\b": "टिप",
    r"\bactive\b": "एक्टिव",
    r"\bmode\b": "मोड",
    r"\bcustomer\b": "कस्टमर",
    r"\bagent\b": "एजेंट",
    r"\bcatalog\b": "कैटलॉग",
    r"\bgrowth\b": "ग्रोथ",
    r"\breturn\b": "रिटर्न",
    r"\brefund\b": "रिफंड",
    r"\bexchange\b": "एक्सचेंज",
    r"\border\b": "ऑर्डर",
    r"\borders\b": "ऑर्डर",
    r"\bprice\b": "प्राइस",
    r"\bdelivery\b": "डिलीवरी",
    r"\bcod\b": "सीओडी",
    r"\bstock\b": "स्टॉक",
    r"\bmargin\b": "मार्जिन",
    r"\bmargins\b": "मार्जिन",
    r"\bsunita\b": "सुनीता",
    r"\bdidi\b": "दीदी",
    r"\bsuneeta\b": "सुनीता",
    r"\bsakhi\b": "सखी",
    r"\bai\b": "एआई",
}

_TRANSLITERATION_RULES = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in _TRANSLITERATION_MAP.items()
]

_RUPEE_PATTERN = re.compile(r"\u20B9\s?(\d[\d,]*)")
_TTS_WHITELIST_PATTERN = re.compile(r"[^a-zA-Z0-9\u0900-\u097F\u0964\u0965 ,.?!]")

def sanitize_for_tts(text: str) -> str:
    # 1. Normalize currency
    text = _RUPEE_PATTERN.sub(lambda m: f"{m.group(1)} \u0930\u0941\u092A\u092F\u0947", text)
    
    # 2. Transliterate common English words to Devanagari
    for pattern, replacement in _TRANSLITERATION_RULES:
        text = pattern.sub(replacement, text)
        
    # 3. Strip any remaining English/Latin letters to prevent Sarvam failures
    text = re.sub(r"[a-zA-Z]", "", text)
    
    # 4. Whitelist only Devanagari characters, digits, spaces, and punctuation
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
