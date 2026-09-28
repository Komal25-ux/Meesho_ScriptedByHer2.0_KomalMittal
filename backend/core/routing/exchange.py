import json
import logging
from typing import Literal
from pydantic import BaseModel, ValidationError
from backend.core.gemini_utils import generate_with_fallback
from backend.core.constants import AFFIRMATIVE_KEYWORDS

logger = logging.getLogger("sakhi-backend")

__all__ = ["ExchangeConfirmationIntent", "classify_exchange_confirmation"]


class ExchangeConfirmationIntent(BaseModel):
    intent: Literal["accept", "decline"]


def classify_exchange_confirmation(user_input: str) -> str:
    """Buckets the customer's reply to an offered exchange/replacement into
    accept (Scenario E) or decline (falls back to Scenario A - Hard Return)."""
    prompt = f"""The customer was just offered an exchange/replacement for their return. They replied: "{user_input}"

Classify into EXACTLY ONE:
- "accept": they agree to the offered exchange/replacement (e.g. "haan thik hai", "ok bhej do", "chalega", "yes").
- "decline": they do not want it and would rather return for a refund (e.g. "nahi", "refund hi chahiye", "wapas karna hai").

Output ONLY valid JSON: {{"intent": "accept"|"decline"}}"""
    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = ExchangeConfirmationIntent(**json.loads(cleaned))
            return parsed.intent
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Exchange confirmation classification failed to parse ({e}); using keyword fallback.")

    lower = user_input.strip().lower()
    if any(k in lower for k in AFFIRMATIVE_KEYWORDS):
        return "accept"
    return "decline"
