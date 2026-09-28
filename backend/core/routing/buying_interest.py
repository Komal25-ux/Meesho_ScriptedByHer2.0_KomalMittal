import json
import logging
from pydantic import BaseModel, ValidationError

from backend.core.gemini_utils import generate_with_fallback

logger = logging.getLogger("sakhi-backend")

__all__ = ["BuyingInterestIntent", "classify_buying_interest"]


class BuyingInterestIntent(BaseModel):
    interested: bool


def classify_buying_interest(user_input: str, product_name: str) -> bool:
    """Backs the Latest Context Lock (see FRESH_BROADCAST_LOCK): broader than
    Priority 2's strict purchase-confirmation classifier in run_customer_agent,
    since a customer's very first reaction to a just-posted product ("I want
    to buy", "details bhejo", "kitne ka hai") is high interest, not yet a
    checkout confirmation - but it still deserves to bind straight to that
    product, not fall through to a fresh ambiguous-match search. Only decides
    whether THIS message is about the just-posted product at all; false
    correctly lets an unrelated first reply (a greeting, a return, a totally
    different category) fall through to normal intent detection instead of
    being force-bound to it."""
    prompt = f"""A product was just posted/shared with a customer on WhatsApp:
Product: {product_name}

Their very next message was: "{user_input}"

Does this message show interest in buying, ordering, or getting details/price about THIS product (e.g.
"I want to buy", "details do", "price kya hai", "haan bhejo", "interested hu", "order kar do", "kitne ka
hai")? Answer false if the message is clearly about something unrelated - a different product/category, a
return/complaint, a greeting, or an unrelated topic.

Output ONLY valid JSON: {{"interested": true|false}}"""
    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = BuyingInterestIntent(**json.loads(cleaned))
            return parsed.interested
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Buying interest classification failed to parse ({e}); using keyword fallback.")

    # Emergency fallback only - used if Gemini is entirely unreachable.
    lower = user_input.strip().lower()
    return any(k in lower for k in [
        "buy", "khareed", "chahiye", "order", "price", "detail", "kitne", "interested",
        "lena", "le lo", "de do", "bhejo", "haan", "chalega", "milega", "available"
    ])
