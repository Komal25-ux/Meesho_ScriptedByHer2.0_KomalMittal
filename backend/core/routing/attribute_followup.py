import logging
from pydantic import BaseModel

from backend.core.gemini_utils import generate_with_fallback
from backend.core.routing.keywords import mentions
from backend.core.routing.llm_json import parse_verdict
from backend.core.prompt_safety import USER_TEXT_RULE, quote_user_text

_COMPLAINT_WORDS = ["chota", "chhota", "bada", "tight", "loose", "kharab", "phat*", "pasand nahi", "achha nahi"]
_ATTRIBUTE_WORDS = [
    "size*", "colour*", "color*", "rang", "material", "fabric", "kapda", "price", "kimat", "keemat",
    "kitne ka", "kitne ki", "available", "stock",
]

logger = logging.getLogger("sakhi-backend")

__all__ = ["AttributeFollowupIntent", "classify_attribute_followup"]


class AttributeFollowupIntent(BaseModel):
    is_followup: bool


def classify_attribute_followup(user_input: str, product_name: str) -> bool:
    """Deterministic Drill-Down gate for run_customer_agent, checked BEFORE
    category extraction / vector search even run (see the call site). This
    exists because leaving the decision to the main customer_prompt's Rule 3b
    was not reliable in practice: a bare attribute word next to a category
    name (e.g. "suit ka size kya hai") can make extract_category_intent
    misread it as a fresh category browse, populating CONTEXT with several
    unrelated same-category products BEFORE the main LLM call ever gets a
    chance to recognize this was actually about the one item already
    established - resurfacing the ambiguous-match picker instead of just
    answering. Running this cheap, narrowly-scoped check first, using ONLY
    the established product's name (never a fresh search), avoids that
    entirely."""
    prompt = f"""A customer was just discussing this product: "{product_name}"

Their next message was:
{quote_user_text(user_input)}
{USER_TEXT_RULE}

Is this message a QUESTION asking about an ATTRIBUTE of THIS SAME product - size, color, material,
fabric, price, availability, or return/exchange policy (e.g. "size kya hai", "colors kya hain", "kitne ka
hai", "cotton hai kya", "return ho sakta hai kya", "kaunse sizes available hain") - without naming any
different/new product or category?

Answer false for all of these: a request to browse/see a different item or category (e.g. "kurti dikhao",
"aur options dikhao"), a purchase confirmation (e.g. "order kar do", "ye lena hai"), a COMPLAINT or
dissatisfaction about size/fit/color/quality (e.g. "size chota hai", "color pasand nahi aaya" - these are
returns, not inquiries), a greeting, or anything unrelated to this specific product's attributes.

Output ONLY valid JSON: {{"is_followup": true|false}}"""
    verdict = parse_verdict(generate_with_fallback(prompt), AttributeFollowupIntent)
    if verdict:
        return verdict.is_followup
    logger.warning("Attribute follow-up: no usable LLM verdict; using keyword fallback.")

    # Outage-only. Deliberately excludes "return"/"exchange": a keyword check
    # can't tell "return ho sakta hai kya" (an inquiry) from "return karna
    # hai" (a real return, which Priority 1 must still catch), so it stays
    # conservative and lets both fall through to the normal flow. A complaint
    # word vetoes everything: "size chota hai" is a return, not a question.
    if mentions(user_input, _COMPLAINT_WORDS):
        return False
    return mentions(user_input, _ATTRIBUTE_WORDS)
