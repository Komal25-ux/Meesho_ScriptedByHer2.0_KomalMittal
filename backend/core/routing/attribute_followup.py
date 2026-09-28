import json
import logging
from pydantic import BaseModel, ValidationError

from backend.core.gemini_utils import generate_with_fallback

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

Their next message was: "{user_input}"

Is this message a QUESTION asking about an ATTRIBUTE of THIS SAME product - size, color, material,
fabric, price, availability, or return/exchange policy (e.g. "size kya hai", "colors kya hain", "kitne ka
hai", "cotton hai kya", "return ho sakta hai kya", "kaunse sizes available hain") - without naming any
different/new product or category?

Answer false for all of these: a request to browse/see a different item or category (e.g. "kurti dikhao",
"aur options dikhao"), a purchase confirmation (e.g. "order kar do", "ye lena hai"), a COMPLAINT or
dissatisfaction about size/fit/color/quality (e.g. "size chota hai", "color pasand nahi aaya" - these are
returns, not inquiries), a greeting, or anything unrelated to this specific product's attributes.

Output ONLY valid JSON: {{"is_followup": true|false}}"""
    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = AttributeFollowupIntent(**json.loads(cleaned))
            return parsed.is_followup
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Attribute follow-up classification failed to parse ({e}); using keyword fallback.")

    # Emergency fallback only - used if Gemini is entirely unreachable.
    # Deliberately excludes "return"/"exchange" here: a keyword-only check
    # can't reliably tell "return ho sakta hai kya" (an inquiry) apart from
    # "return karna hai" (a genuine return request that Priority 1 must still
    # catch), so during a total outage this stays conservative and lets those
    # fall through to the normal flow instead of risking a swallowed return.
    lower = user_input.strip().lower()
    complaint_words = ["chota", "bada", "tight", "loose", "kharab", "phata", "pasand nahi", "achha nahi"]
    if any(w in lower for w in complaint_words):
        return False
    attribute_words = ["size", "colour", "color", "rang", "material", "fabric", "kapda", "price", "kimat", "kitne ka", "available", "stock"]
    return any(w in lower for w in attribute_words)
