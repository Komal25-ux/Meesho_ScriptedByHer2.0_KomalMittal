import logging
from typing import Literal
from pydantic import BaseModel
from backend.core.gemini_utils import generate_with_fallback
from backend.core.routing.keywords import mentions
from backend.core.routing.llm_json import parse_verdict
from backend.core.prompt_safety import USER_TEXT_RULE, quote_user_text

_DEFECT_WORDS = ["phat*", "kharab", "daag", "defect*", "damage*", "toot*", "ganda"]
_SIZE_WORDS = ["size", "sizing", "chota", "chhota", "choti", "chhoti", "bada", "badi", "tight", "loose", "fit*"]
_LOOK_WORDS = ["color*", "colour*", "rang", "style", "design", "pasand nahi", "achha nahi lag*"]

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
return for "{product_name}" and was just asked what went wrong. They replied:
{quote_user_text(user_input)}
{USER_TEXT_RULE}

Classify their grievance into EXACTLY ONE bucket:
- "hard_return": they insist on returning / want a refund and refuse any exchange. E.g. "Nahi, mujhe waapis hi karna hai", "Paise waapis chahiye".
- "size_issue": complaint about fit. E.g. "Suit chota hai", "Size tight hai", "Bada ho gaya".
- "color_style_issue": doesn't like the look/color. E.g. "Color achha nahi lag raha", "Style pasand nahi aayi".
- "defective": reports damage or a manufacturing defect. E.g. "Phata hua hai", "Kharab hai", "Daag laga hai".

Output ONLY valid JSON: {{"scenario": "hard_return"|"size_issue"|"color_style_issue"|"defective"}}"""
    verdict = parse_verdict(generate_with_fallback(prompt), ReturnGrievanceIntent)
    if verdict:
        return verdict.scenario
    logger.warning("Return grievance: no usable LLM verdict; using keyword fallback.")
    return _grievance_fallback(user_input)


def _grievance_fallback(user_input: str) -> str:
    """Outage-only. When a message names more than one problem the most
    serious wins - defect, then size, then look - and with none named the
    customer is treated as wanting a plain return."""
    if mentions(user_input, _DEFECT_WORDS):
        return "defective"
    if mentions(user_input, _SIZE_WORDS):
        return "size_issue"
    if mentions(user_input, _LOOK_WORDS):
        return "color_style_issue"
    return "hard_return"
