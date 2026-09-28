import json
import logging
from typing import Optional, Literal
from pydantic import BaseModel, ValidationError
from backend.core.gemini_utils import generate_with_fallback
from backend.core.constants import (
    REAL_CATEGORIES,
    _CATEGORY_KEYWORDS,
    _MORE_KEYWORDS,
    _NON_BROWSE_KEYWORDS,
)

logger = logging.getLogger("sakhi-backend")

__all__ = ["CategoryIntent", "extract_category_intent"]


class CategoryIntent(BaseModel):
    category: Literal["sarees", "kurtis", "suits", "tops", "lehengas", "dresses", "same", "none"]


def extract_category_intent(user_input: str, last_category: Optional[str]) -> Optional[str]:
    """Determines which real product category (if any) this message is a
    genuine BROWSE request for - the signal category-strict retrieval uses
    to narrow db_client.match_products (see run_customer_agent/
    run_catalog_agent), NOT a general "did this category get mentioned"
    detector, and NOT itself a routing decision.

    This distinction is load-bearing, not cosmetic: a message like "saree
    wapas karni hai" (a return) also names a category, but "saree" there is
    incidental - the message isn't a request to browse sarees. Extracting a
    category for it anyway was tried first and caused a real regression: the
    aggressive category-scoped fetch (threshold=0, up to 100 candidates - see
    match_products) filled CONTEXT with 4 unrelated sarees, and that
    unexpectedly-populated CONTEXT was enough to distract the main LLM call
    away from correctly firing Priority 1 (Return Retention Hook) in favor of
    treating it as a browse. So this only ever returns a category when
    browsing/seeing products is the message's actual primary intent.

    Returns one of REAL_CATEGORIES, None (no genuine browse-category intent -
    a fully generic query, or the message is about something else entirely
    even if it happens to name a category), or the caller's own
    `last_category` echoed back for a bare continuation request like "aur
    dikhao" with no new category named.
    """
    prompt = f"""You are extracting a product CATEGORY BROWSE request from a Hindi/Hinglish message - nothing else.

Real categories (ONLY these are valid): sarees, kurtis, suits, tops, lehengas, dresses.
This session's currently active category (if any): {last_category or "none"}.

Message: "{user_input}"

Classify into EXACTLY ONE:
- One of the 6 category names above, ONLY if the message's PRIMARY intent is to browse/see products in that category (e.g. "saree dikhao", "kurti chahiye", "suits available hai kya", "mujhe achi si saree chahiye"). A category word appearing in the message is NOT enough by itself.
- "same": the message is a continuation asking for more of what was already being browsed, with no new category named (e.g. "aur dikhao", "kuch aur options", "more please", "aur kya hai").
- "none": EITHER the message doesn't reference any product category at all, OR it names a category but its primary intent is something else entirely - a return/refund/exchange/complaint (e.g. "saree wapas karni hai"), a purchase confirmation (e.g. "isse order kardo"), or a question about one already-identified specific item. Those are NOT browse requests even though they may mention a category - output "none" for all of them.

Output ONLY valid JSON: {{"category": "sarees"|"kurtis"|"suits"|"tops"|"lehengas"|"dresses"|"same"|"none"}}"""
    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = CategoryIntent(**json.loads(cleaned))
            if parsed.category == "none":
                return None
            if parsed.category == "same":
                return last_category
            return parsed.category
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Category intent extraction failed to parse ({e}); using keyword fallback.")

    lower = user_input.strip().lower()
    if any(kw in lower for kw in _NON_BROWSE_KEYWORDS):
        # Return/purchase/specific-item signal present - never a browse
        # request regardless of any category word also present.
        return None
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return cat
    if last_category and any(kw in lower for kw in _MORE_KEYWORDS):
        return last_category
    return None
