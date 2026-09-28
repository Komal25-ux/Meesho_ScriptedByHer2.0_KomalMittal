import json
import logging
from typing import Literal
from pydantic import BaseModel, ValidationError
from backend.core.gemini_utils import generate_with_fallback
from backend.core.constants import (
    _RETURNS_STAGE_LABELS,
    _RETURNS_FALLBACK_TEXT,
)

logger = logging.getLogger("sakhi-backend")

__all__ = ["ReturnGrievanceIntent", "classify_return_grievance"]


class ReturnGrievanceIntent(BaseModel):
    scenario: Literal["hard_return", "size_issue", "color_style_issue", "defective"]


def classify_return_grievance(user_input: str, product_name: str) -> str:
    """Buckets the customer's first reply to a return outreach into Scenario
    A/B/C/D of the Returns Retention Funnel. An LLM call, not keyword
    matching, for the same reason classify_approval_intent is one: phrasing
    here is too free-form for reliable substring checks (e.g. "chota hai"
    alone is ambiguous between "runs small" and "got smaller/damaged")."""
    prompt = f"""You are an intent router for a Meesho Returns Retention flow. The customer initiated a
return for "{product_name}" and was just asked what went wrong. They replied: "{user_input}"

Classify their grievance into EXACTLY ONE bucket:
- "hard_return": they insist on returning / want a refund and refuse any exchange. E.g. "Nahi, mujhe waapis hi karna hai", "Paise waapis chahiye".
- "size_issue": complaint about fit. E.g. "Suit chota hai", "Size tight hai", "Bada ho gaya".
- "color_style_issue": doesn't like the look/color. E.g. "Color achha nahi lag raha", "Style pasand nahi aayi".
- "defective": reports damage or a manufacturing defect. E.g. "Phata hua hai", "Kharab hai", "Daag laga hai".

Output ONLY valid JSON: {{"scenario": "hard_return"|"size_issue"|"color_style_issue"|"defective"}}"""
    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = ReturnGrievanceIntent(**json.loads(cleaned))
            return parsed.scenario
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Return grievance classification failed to parse ({e}); using keyword fallback.")

    # Emergency fallback only - used if Gemini is entirely unreachable.
    lower = user_input.strip().lower()
    if any(w in lower for w in ["phata", "kharab", "daag", "defect", "damage", "toota"]):
        return "defective"
    if any(w in lower for w in ["size", "chota", "bada", "tight", "loose", "fit"]):
        return "size_issue"
    if any(w in lower for w in ["color", "rang", "style", "pasand nahi"]):
        return "color_style_issue"
    return "hard_return"
