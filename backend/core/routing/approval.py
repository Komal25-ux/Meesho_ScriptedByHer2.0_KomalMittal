import logging
from typing import Dict, Any, Literal
from pydantic import BaseModel
from backend.core.gemini_utils import generate_with_fallback
from backend.core.routing.keywords import mentions
from backend.core.routing.llm_json import parse_verdict
from backend.core.prompt_safety import USER_TEXT_RULE, quote_user_text
from backend.core.constants import AFFIRMATIVE_KEYWORDS, NEGATIVE_KEYWORDS
from backend.core.pricing import requested_price

logger = logging.getLogger("sakhi-backend")

__all__ = ["ApprovalIntent", "classify_approval_intent"]


class ApprovalIntent(BaseModel):
    intent: Literal["approve", "modify", "new_request"]


def classify_approval_intent(user_input: str, pending: Dict[str, Any]) -> str:
    """Semantic router for a reply to a pending catalog draft, replacing keyword
    matching that collided on "kar do"/"kardo" - a phrase that shows up equally
    in a genuine approval ("haan kar do"), a price edit ("price 599 kardo"), and
    an ordinary new listing request ("blue kurti list kardo"). An LLM call can
    actually tell these apart from context; a keyword substring check can't."""
    prompt = f"""You are an intent router for a Hindi/Hinglish e-commerce bot. The reseller has a pending catalog draft waiting for approval:

Product: {pending.get('matched_product_name')}
Current Price: ₹{pending.get('selling_price')}

The reseller just replied:
{quote_user_text(user_input)}
{USER_TEXT_RULE}

Classify their response into EXACTLY ONE of these buckets:
- "approve": they want to post/confirm the draft as-is (e.g. "haan kar do", "post kar do", "theek hai", "confirm").
- "modify": they want to change the price or details of THIS SAME draft (e.g. "nahi, price 599 kar do", "isse 799 me list kar do", "price kam karo").
- "new_request": they are ignoring this draft entirely and asking about something else - a different item, or an unrelated request (e.g. "blue kurti list kardo", "weekly sales dikhao", "nahi rehne do", "customer ne return maanga").

Output ONLY valid JSON: {{"intent": "approve" | "modify" | "new_request"}}"""

    verdict = parse_verdict(generate_with_fallback(prompt), ApprovalIntent)
    if verdict:
        return verdict.intent
    logger.warning("Approval intent: no usable LLM verdict; using keyword fallback.")
    return _approval_fallback(user_input)


def _approval_fallback(user_input: str) -> str:
    """Outage-only rules, first match wins:
    1. a price is named           -> "modify" ("nahi, 599 kar do" is a price change)
    2. any refusal word           -> "new_request" (an unclear yes/no never publishes)
    3. an affirmative             -> "approve"
    4. anything else              -> "new_request"
    Refusal is checked before agreement: "kal confirm karungi, abhi ruko"
    used to approve the draft because it contains "confirm".
    """
    if requested_price(user_input):
        return "modify"
    if mentions(user_input, NEGATIVE_KEYWORDS):
        return "new_request"
    if mentions(user_input, AFFIRMATIVE_KEYWORDS):
        return "approve"
    return "new_request"
