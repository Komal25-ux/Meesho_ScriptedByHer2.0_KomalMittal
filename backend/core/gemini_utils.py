import logging
import google.generativeai as genai
from backend.config import settings

logger = logging.getLogger("sakhi-backend")

def configure_gemini() -> bool:
    if settings.GEMINI_API_KEY and "YOUR_GEMINI" not in settings.GEMINI_API_KEY:
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            return True
        except Exception as e:
            logger.error(f"Gemini API configuration failed: {e}")
    return False

# The free tier enforces a per-model daily request quota, not a per-key one -
# trying several models in order means one model running dry doesn't stall
# every agent, since each model has its own separate quota bucket.
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-2.0-flash-lite"]

def _model_chain():
    chain = [settings.GEMINI_MODEL]
    for m in FALLBACK_MODELS:
        if m not in chain:
            chain.append(m)
    return chain

def generate_with_fallback(parts):
    """Tries each model in the fallback chain in order, moving to the next on
    any failure (quota exhaustion, retirement, transient error). `parts` is
    whatever genai.GenerativeModel.generate_content accepts - a prompt string,
    or a list mixing text with {"mime_type": ..., "data": ...} blocks for
    multimodal input. Returns the response text, or None if every model failed."""
    if not configure_gemini():
        return None
    last_error = None
    for model_name in _model_chain():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(parts)
            text = response.text.strip()
            if text:
                return text
        except Exception as e:
            last_error = e
            logger.warning(f"Gemini model '{model_name}' failed, trying next fallback: {e}")
            continue
    logger.error(f"All Gemini fallback models failed. Last error: {last_error}")
    return None
