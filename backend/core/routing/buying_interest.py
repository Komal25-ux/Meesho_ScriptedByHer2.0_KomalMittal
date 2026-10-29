import logging
from pydantic import BaseModel

from backend.core.gemini_utils import generate_with_fallback
from backend.core.constants import NEGATIVE_KEYWORDS
from backend.core.routing.keywords import mentions
from backend.core.routing.llm_json import parse_verdict
from backend.core.prompt_safety import USER_TEXT_RULE, quote_user_text

_INTEREST_WORDS = [
    "buy*", "khareed*", "chahiye", "order*", "price", "detail*", "kitne", "interested",
    "lena", "le lo", "lelo", "de do", "bhejo", "haan", "chalega", "milega", "available",
]

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

Their very next message was:
{quote_user_text(user_input)}
{USER_TEXT_RULE}

Does this message show interest in buying, ordering, or getting details/price about THIS product (e.g.
"I want to buy", "details do", "price kya hai", "haan bhejo", "interested hu", "order kar do", "kitne ka
hai")? Answer false if the message is clearly about something unrelated - a different product/category, a
return/complaint, a greeting, or an unrelated topic.

Output ONLY valid JSON: {{"interested": true|false}}"""
    verdict = parse_verdict(generate_with_fallback(prompt), BuyingInterestIntent)
    if verdict:
        return verdict.interested
    logger.warning("Buying interest: no usable LLM verdict; using keyword fallback.")
    # Outage-only. A refusal outweighs any interest word: "nahi chahiye"
    # contains "chahiye" and used to count as interest.
    if mentions(user_input, NEGATIVE_KEYWORDS):
        return False
    return mentions(user_input, _INTEREST_WORDS)
