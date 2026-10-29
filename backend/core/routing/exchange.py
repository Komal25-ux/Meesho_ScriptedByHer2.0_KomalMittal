import logging
from typing import Literal
from pydantic import BaseModel
from backend.core.gemini_utils import generate_with_fallback
from backend.core.constants import AFFIRMATIVE_KEYWORDS, NEGATIVE_KEYWORDS
from backend.core.routing.keywords import mentions
from backend.core.routing.llm_json import parse_verdict
from backend.core.prompt_safety import USER_TEXT_RULE, quote_user_text

_WANTS_REFUND = ["refund*", "wapas", "waapis", "paise"]

logger = logging.getLogger("sakhi-backend")

__all__ = ["ExchangeConfirmationIntent", "classify_exchange_confirmation"]


class ExchangeConfirmationIntent(BaseModel):
    intent: Literal["accept", "decline"]


def classify_exchange_confirmation(user_input: str) -> str:
    """Buckets the customer's reply to an offered exchange/replacement into
    accept (Scenario E) or decline (falls back to Scenario A - Hard Return)."""
    prompt = f"""The customer was just offered an exchange/replacement for their return. They replied:
{quote_user_text(user_input)}
{USER_TEXT_RULE}

Classify into EXACTLY ONE:
- "accept": they agree to the offered exchange/replacement (e.g. "haan thik hai", "ok bhej do", "chalega", "yes").
- "decline": they do not want it and would rather return for a refund (e.g. "nahi", "refund hi chahiye", "wapas karna hai").

Output ONLY valid JSON: {{"intent": "accept"|"decline"}}"""
    verdict = parse_verdict(generate_with_fallback(prompt), ExchangeConfirmationIntent)
    if verdict:
        return verdict.intent
    logger.warning("Exchange confirmation: no usable LLM verdict; using keyword fallback.")
    return _exchange_fallback(user_input)


def _exchange_fallback(user_input: str) -> str:
    """Outage-only: any refusal or refund word declines, then an explicit yes
    accepts, and anything unclear declines - the customer is sent to the
    refund they can always fall back on, never into an exchange they didn't
    clearly agree to."""
    if mentions(user_input, NEGATIVE_KEYWORDS + _WANTS_REFUND):
        return "decline"
    if mentions(user_input, AFFIRMATIVE_KEYWORDS + ["bhej do", "exchange*"]):
        return "accept"
    return "decline"
