import re
from typing import List, Dict, Tuple

__all__ = [
    "CATALOG_SHARE_TRIGGER_RE",
    "CUSTOMER_DETAILS_TRIGGER_RE",
    "REAL_CATEGORIES",
    "AFFIRMATIVE_KEYWORDS",
    "NEGATIVE_KEYWORDS",
    "_CATEGORY_KEYWORDS",
    "_MORE_KEYWORDS",
    "_NON_BROWSE_KEYWORDS",
    "_RETURNS_STAGE_LABELS",
    "_RETURNS_FALLBACK_TEXT",
    "CUSTOMER_ZERO_HALLUCINATION_REFUSAL",
    "CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS",
    "DRILL_DOWN_CTA",
    "DRILL_DOWN_CTA_TTS",
]

# Deterministic Product Card Click triggers (see handleProductCardClick in
# App.jsx) - a mode-aware wrapper the frontend sends instead of a bare
# product name whenever ANY product card is tapped (a fresh ambiguous-match
# picker OR an old card scrolled back up to), since a bare name gives
# detect_intent's LLM classifier no verb/intent signal to route confidently.
# Defined once here (not duplicated per-function) since detect_intent,
# check_pending_selection, run_catalog_agent, and run_customer_agent all need
# to recognize/strip the exact same prefix.
CATALOG_SHARE_TRIGGER_RE = re.compile(r"^ye item whatsapp group mein share karna hai:\s*", re.IGNORECASE)
CUSTOMER_DETAILS_TRIGGER_RE = re.compile(r"^mujhe ye wala item pasand hai,?\s*iski details batao:\s*", re.IGNORECASE)

# The real catalog categories (see scripts/seed_catalog.py's build_catalog) -
# the only values category-strict retrieval is ever allowed to filter by.
# Whitelisted rather than trusting the LLM's raw string output, so a
# hallucinated/mistyped category (or one that doesn't exist, e.g.
# "jewellery") can never silently filter every candidate out and falsely
# trigger the exhaustion message.
REAL_CATEGORIES: List[str] = ["sarees", "kurtis", "suits", "tops", "lehengas", "dresses"]

# Kept only as the last-resort fallback for classify_approval_intent() below,
# used if the Gemini call itself is unreachable. The primary router is an LLM
# classification, not keyword matching - see classify_approval_intent().
AFFIRMATIVE_KEYWORDS: List[str] = [
    "haan", "haa", "ha ", "yes", "kar do", "kardo", "confirm",
    "post kar", "theek hai", "thik hai", "ok", "okay", "sahi hai",
    "post karo", "chalo"
]
NEGATIVE_KEYWORDS: List[str] = [
    "nahi", "no", "cancel", "mat karo", "ruko", "rehne do", "abhi nahi"
]

# Keyword fallback for extract_category_intent - only used if Gemini is
# unreachable, same reasoning as every other classifier's keyword fallback
# in this file.
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "sarees": ["saree", "sari"],
    "kurtis": ["kurti", "kurta"],
    "suits": ["suit"],
    "tops": ["top"],
    "lehengas": ["lehenga", "lehnga"],
    "dresses": ["dress"],
}

_MORE_KEYWORDS: List[str] = ["aur", "kuch aur", "more", "another", "next", "baaki", "dikhao"]

# If any of these fire alongside a category word, the message is NOT a
# browse request (it's a return/purchase/specific-item message that merely
# mentions a category in passing) - see extract_category_intent's docstring.
_NON_BROWSE_KEYWORDS: List[str] = [
    "wapas", "return", "exchange", "badalna", "refund", "kharab", "defect",
    "order", "khareed", "pack kar", "confirm", "book", "lelo", "le lo", "isse", "isko", "iska"
]

_RETURNS_STAGE_LABELS: Dict[str, str] = {
    "A": "SCENARIO A - Hard Return",
    "B": "SCENARIO B - Size Issue",
    "C": "SCENARIO C - Color/Style Issue",
    "D": "SCENARIO D - Defective/Damaged Issue",
    "E": "SCENARIO E - Exchange Accepted (closing the loop)",
}

# Exact mandated strings, used both as prompt instructions AND as the hard
# fallback if every model in the fallback chain fails outright - same reasoning
# as CUSTOMER_ZERO_HALLUCINATION_REFUSAL: a canned Python constant guarantees
# the exact wording with zero hallucination risk regardless of LLM output.
_RETURNS_FALLBACK_TEXT: Dict[str, Tuple[str, str]] = {
    "A": (
        "Koi baat nahi! Humein khed hai ki product aapki ummeedon par khara nahi utra. Maine return request Sunita Didi ko forward kar di hai, wo jald hi refund process kar dengi. 🙏",
        "कोई बात नहीं! हमें खेद है कि प्रोडक्ट आपकी उम्मीदों पर खरा नहीं उतरा. मैंने रिटर्न रिक्वेस्ट सुनीता दीदी को फॉरवर्ड कर दी है, वो जल्द ही रिफंड प्रोसेस कर देंगी.",
    ),
    "D": (
        "Oh no! Maaf kijiyega ki aapko kharab product mila. Kya main iski jagah naya piece bhej dun, ya aap refund chahenge?",
        "ओह नो! माफ़ कीजियेगा की आपको ख़राब प्रोडक्ट मिला. क्या मैं इसकी जगह नया पीस भेज दूँ, या आप रिफंड चाहेंगे?",
    ),
    "E": (
        "Great! Maine aapki exchange request note kar li hai. Sunita Didi jald hi naye order ki dispatch details aapko bhej dengi. 🛍️",
        "ग्रेट! मैंने आपकी एक्सचेंज रिक्वेस्ट नोट कर ली है. सुनीता दीदी जल्द ही नए आर्डर की डिस्पैच डिटेल्स आपको भेज देंगी.",
    ),
}

CUSTOMER_ZERO_HALLUCINATION_REFUSAL = "Maaf kijiyega, mere pas abhi iski detail nahi hai. Mai Didi se puch kar batati hu."
CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS = "माफ़ कीजिएगा, मेरे पास अभी इसकी डिटेल नहीं है. मैं दीदी से पूछ कर बताती हूँ."

# Exact closing question appended to every Drill-Down State reply (Rule 3b -
# see customer_prompt) - guaranteed in Python, not left to the model alone,
# same reasoning as every other hard-mandated string in this file: a canned
# constant can't be dropped by an off-spec generation.
DRILL_DOWN_CTA = "kya isse order kar dun?"
DRILL_DOWN_CTA_TTS = "क्या इसे ऑर्डर कर दूं?"
