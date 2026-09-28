import re
import json
import logging
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, ValidationError
from backend.core.gemini_utils import generate_with_fallback
from backend.core.constants import AFFIRMATIVE_KEYWORDS, NEGATIVE_KEYWORDS

logger = logging.getLogger("sakhi-backend")

__all__ = ["ApprovalIntent", "classify_approval_intent", "_extract_price"]


def _extract_price(text: str) -> Optional[int]:
    """Pulls the first standalone number out of a message, e.g. "price 599 kar
    do" -> 599. Used to detect a price-change request during pending approval."""
    match = re.search(r"\b(\d{2,6})\b", text)
    return int(match.group(1)) if match else None


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

The reseller just said: "{user_input}"

Classify their response into EXACTLY ONE of these buckets:
- "approve": they want to post/confirm the draft as-is (e.g. "haan kar do", "post kar do", "theek hai", "confirm").
- "modify": they want to change the price or details of THIS SAME draft (e.g. "nahi, price 599 kar do", "isse 799 me list kar do", "price kam karo").
- "new_request": they are ignoring this draft entirely and asking about something else - a different item, or an unrelated request (e.g. "blue kurti list kardo", "weekly sales dikhao", "nahi rehne do", "customer ne return maanga").

Output ONLY valid JSON: {{"intent": "approve" | "modify" | "new_request"}}"""

    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = ApprovalIntent(**json.loads(cleaned))
            return parsed.intent
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Approval intent classification failed to parse ({e}); using keyword fallback.")

    # Emergency fallback only - used if Gemini is entirely unreachable, so the
    # human-in-the-loop flow doesn't hard-fail with no path forward.
    lower = user_input.strip().lower()
    if any(k in lower for k in AFFIRMATIVE_KEYWORDS) and not _extract_price(user_input):
        return "approve"
    if _extract_price(user_input):
        return "modify"
    if any(k in lower for k in NEGATIVE_KEYWORDS):
        return "new_request"
    return "new_request"
