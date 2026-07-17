import time
import json
import logging
from typing import TypedDict, Optional, List, Dict, Any, Literal
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, ValidationError
import google.generativeai as genai
from backend.config import settings
from backend.db.supabase_client import db_client
from backend.core.gemini_utils import configure_gemini, generate_with_fallback, generate_structured_with_fallback, AgentResponse, CatalogCaptionResponse, CustomerAgentResponse, ReturnsAgentResponse
from backend.core.image_compositor import generate_ad_creative

logger = logging.getLogger("sakhi-backend")

# In-memory store for catalog listings awaiting reseller approval, keyed by
# whatsapp_number + active_mode. A single-process prototype dict is sufficient
# here since there's no multi-worker deployment; a real deployment would
# persist this (e.g. a Supabase table) so approval survives across server
# restarts/workers.
#
# Keying by whatsapp_number alone previously meant Reseller and Customer mode
# shared the same pending-approval slot (both send the same whatsapp_number),
# so a draft awaiting confirmation in Reseller mode would bleed into Customer
# mode's chat. Namespacing the key by mode isolates them.
PENDING_LISTINGS: Dict[str, Dict[str, Any]] = {}

def _pending_key(whatsapp_number: str, active_mode: str) -> str:
    return f"{whatsapp_number}::{active_mode}"

# Kept only as the last-resort fallback for classify_approval_intent() below,
# used if the Gemini call itself is unreachable. The primary router is an LLM
# classification, not keyword matching - see classify_approval_intent().
AFFIRMATIVE_KEYWORDS = ["haan", "haa", "ha ", "yes", "kar do", "kardo", "confirm", "post kar", "theek hai", "thik hai", "ok", "okay", "sahi hai", "post karo", "chalo"]
NEGATIVE_KEYWORDS = ["nahi", "no", "cancel", "mat karo", "ruko", "rehne do", "abhi nahi"]

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

# In-memory store for a return in progress awaiting the customer's next reply,
# keyed exactly like PENDING_LISTINGS (whatsapp_number + active_mode) so it
# never bleeds into the Reseller segment. Seeded by run_returns_proactive_outreach
# when the backend system webhook fires (see /api/v1/system/trigger-return) -
# this is the ONLY way a return ever starts. From there, the customer's
# free-text replies are intercepted here turn-by-turn (the graph has no
# persistent thread memory, so without this dict there would be no way to
# know "this customer is mid-return" by the time their next message arrives).
PENDING_RETURNS: Dict[str, Dict[str, Any]] = {}

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

class ExchangeConfirmationIntent(BaseModel):
    intent: Literal["accept", "decline"]

def classify_exchange_confirmation(user_input: str) -> str:
    """Buckets the customer's reply to an offered exchange/replacement into
    accept (Scenario E) or decline (falls back to Scenario A - Hard Return)."""
    prompt = f"""The customer was just offered an exchange/replacement for their return. They replied: "{user_input}"

Classify into EXACTLY ONE:
- "accept": they agree to the offered exchange/replacement (e.g. "haan thik hai", "ok bhej do", "chalega", "yes").
- "decline": they do not want it and would rather return for a refund (e.g. "nahi", "refund hi chahiye", "wapas karna hai").

Output ONLY valid JSON: {{"intent": "accept"|"decline"}}"""
    raw_text = generate_with_fallback(prompt)
    if raw_text:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            parsed = ExchangeConfirmationIntent(**json.loads(cleaned))
            return parsed.intent
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Exchange confirmation classification failed to parse ({e}); using keyword fallback.")

    lower = user_input.strip().lower()
    if any(k in lower for k in AFFIRMATIVE_KEYWORDS):
        return "accept"
    return "decline"

def _embed_text(text: str) -> list:
    if not configure_gemini():
        return []
    try:
        embed_res = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_query",
            output_dimensionality=768
        )
        return embed_res["embedding"]
    except Exception as e:
        logger.error(f"Embedding generation failed in Returns Retention flow: {e}")
        return []

def _lookup_product_by_name(product_name: str) -> Optional[Dict[str, Any]]:
    """Anchors the Returns Retention flow to the actual item being returned by
    semantic-matching its name against the real catalog - never guessed."""
    matches = db_client.match_products(_embed_text(product_name), threshold=0.15, limit=1)
    return matches[0] if matches else None

def _find_alternative_product(original_product: Dict[str, Any], query_hint: str) -> Optional[Dict[str, Any]]:
    """Scenario B/C alternative lookup: real RAG retrieval against the catalog
    only - the model is never allowed to name a product it wasn't given.
    query_hint biases the search toward the customer's actual complaint, and
    the original product is excluded from its own results by product_id."""
    matches = db_client.match_products(
        _embed_text(f"{original_product.get('category', '')} {query_hint}"),
        threshold=0.15,
        limit=3
    )
    for m in matches:
        if m.get("product_id") != original_product.get("product_id"):
            return m
    return None

# ── RETURNS RETENTION FUNNEL SYSTEM PROMPT ────────────────────
# Hardcoded behavioral matrix for the Returns Agent. CURRENT_STAGE and
# ALTERNATIVE_PRODUCT are computed deterministically in Python (see
# check_pending_return below) BEFORE this prompt is ever called - the model
# never decides which scenario applies or invents a product; it only narrates
# the one scenario Python has already selected, using only the grounding data
# Python retrieved via real RAG lookups.
RETURNS_RETENTION_SYSTEM_PROMPT = """
You are 'Returns Didi', the Returns Retention specialist for Meesho reseller {reseller_name}. A
customer has an active return in progress for "{product_name}" (Order #{order_id}). Your job is to
retain the sale wherever genuinely possible - through an exchange - while never pressuring a customer
who truly wants a refund.

CURRENT STAGE FOR THIS TURN: {stage_label}
CUSTOMER JUST SAID: "{user_input}"
{alternative_context}

Only follow the ONE scenario matching CURRENT STAGE above - ignore the others this turn.

SCENARIO A - "Hard Return" (customer insists on returning, or no alternative could be found):
Do not argue or upsell. Gracefully hand off the refund. Set suggests_alternative to false.
You MUST output EXACTLY:
ui_text: "Koi baat nahi! Humein khed hai ki product aapki ummeedon par khara nahi utra. Maine return request Sunita Didi ko forward kar di hai, wo jald hi refund process kar dengi. 🙏"
tts_text: "कोई बात नहीं! हमें खेद है कि प्रोडक्ट आपकी उम्मीदों पर खरा नहीं उतरा. मैंने रिटर्न रिक्वेस्ट सुनीता दीदी को फॉरवर्ड कर दी है, वो जल्द ही रिफंड प्रोसेस कर देंगी."

SCENARIO B - "Size Issue": ALTERNATIVE_PRODUCT above was retrieved from the real catalog for the
customer's fit complaint. Warmly suggest it by name as the fix, state its size, and set
suggests_alternative to true. You cannot hallucinate an alternative - only ever name the exact product
given in ALTERNATIVE_PRODUCT above.

SCENARIO C - "Color/Style Issue": ALTERNATIVE_PRODUCT above was retrieved from the real catalog for
the customer's look/color complaint. Warmly suggest it by name as the alternative, mention its
color/style, and set suggests_alternative to true. You cannot hallucinate an alternative - only ever
name the exact product given in ALTERNATIVE_PRODUCT above.

SCENARIO D - "Defective/Damaged Issue": Apologize immediately for the defect. Set suggests_alternative
to false (no image yet - nothing has been confirmed).
You MUST output EXACTLY:
ui_text: "Oh no! Maaf kijiyega ki aapko kharab product mila. Kya main iski jagah naya piece bhej dun, ya aap refund chahenge?"
tts_text: "ओह नो! माफ़ कीजियेगा की आपको ख़राब प्रोडक्ट मिला. क्या मैं इसकी जगह नया पीस भेज दूँ, या आप रिफंड चाहेंगे?"

SCENARIO E - "Exchange Accepted" (closing the loop, customer just agreed to a prior exchange offer):
Confirm and hand off to the human reseller. Set suggests_alternative to false (they already saw the
image in the previous turn).
You MUST output EXACTLY:
ui_text: "Great! Maine aapki exchange request note kar li hai. Sunita Didi jald hi naye order ki dispatch details aapko bhej dengi. 🛍️"
tts_text: "ग्रेट! मैंने आपकी एक्सचेंज रिक्वेस्ट नोट कर ली है. सुनीता दीदी जल्द ही नए आर्डर की डिस्पैच डिटेल्स आपको भेज देंगी."

STRICT RULES:
- You cannot hallucinate alternatives. Only ever name a product that appears in ALTERNATIVE_PRODUCT
  above - never invent a product, size, or color you were not given.
- You must output your response using the provided JSON schema. Keep responses strictly under 2 short
  sentences, except where an EXACT string is mandated above - reproduce that verbatim.
- In tts_text: never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी".
  Never use currency symbols like "₹" - always spell out the number followed by "रुपये".
"""

class SakhiState(TypedDict):
    reseller_id: str
    whatsapp_number: str
    raw_input: str
    input_type: str
    active_mode: str  # 'reseller' or 'customer' - toggled from the frontend UI

    # Reseller details
    reseller_name: str
    reseller_location: str
    reseller_language: str
    reseller_dialect: str

    # Intent
    detected_intent: str
    intent_confidence: float

    # Human-in-the-loop catalog approval routing (transient, not persisted)
    pending_route: str
    # Human-in-the-loop Returns Retention routing (transient, not persisted)
    pending_return_route: str

    # Processing outputs
    reply_text: str
    reply_audio_b64: Optional[str]
    reply_image_url: Optional[str]
    # Pure Devanagari version of reply_text for Sarvam TTS (dual-output from
    # the same LLM call as reply_text). Falls back to reply_text at the API
    # layer if a node doesn't set this (e.g. deterministic template replies).
    reply_tts_text: Optional[str]

    # Set when a catalog listing was just finalized this turn, so the API
    # layer can broadcast the post into the Customer segment's chat.
    listing_finalized: bool
    listing_broadcast_caption: Optional[str]
    listing_broadcast_caption_tts: Optional[str]

    # Tracking telemetry for dashboard
    trace_logs: List[Dict[str, Any]]

    # DB models context
    context_data: Optional[Dict[str, Any]]

# ── NODE 1: LOAD MEMORY ──────────────────────────────────────
def load_memory(state: SakhiState) -> SakhiState:
    t_start = time.time()
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    
    # Retrieve reseller profile from Supabase
    reseller = db_client.get_or_create_reseller(whatsapp_number)
    profile = db_client.get_reseller_profile(reseller["id"])
    
    state["reseller_id"] = reseller["id"]
    state["reseller_name"] = reseller["name"]
    state["reseller_location"] = reseller.get("location", "Kanpur")
    state["reseller_language"] = reseller.get("language", "hi")
    state["reseller_dialect"] = reseller.get("dialect", "hindi")
    state["context_data"] = {"profile": profile}
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Memory Retrieval",
        "latency_ms": latency,
        "data": {
            "reseller_name": reseller["name"],
            "whatsapp_number": whatsapp_number,
            "dialect": reseller.get("dialect", "hindi")
        }
    }
    state["trace_logs"] = [log_event]
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "memory_retrieval",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    
    return state

# ── NODE 1.5: CHECK PENDING CATALOG APPROVAL (Human-in-the-loop) ──
def _extract_price(text: str) -> Optional[int]:
    """Pulls the first standalone number out of a message, e.g. "price 599 kar
    do" -> 599. Used to detect a price-change request during pending approval."""
    import re
    match = re.search(r"\b(\d{2,6})\b", text)
    return int(match.group(1)) if match else None

def check_pending_approval(state: SakhiState) -> SakhiState:
    """If a catalog draft is awaiting the reseller's approval, intercept the
    turn here instead of running intent detection, so the graph genuinely
    pauses on the draft until the reseller responds to it. The response is
    classified by an LLM (approve / modify / new_request) rather than keyword
    matching, since phrases like "kar do"/"kardo" show up identically in a
    genuine approval, a price edit, and an unrelated new listing request."""
    t_start = time.time()
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    raw_input = state.get("raw_input", "")

    pending_key = _pending_key(whatsapp_number, active_mode)
    pending = PENDING_LISTINGS.get(pending_key)
    if not pending:
        state["pending_route"] = "not_pending"
        return state

    intent = classify_approval_intent(raw_input, pending)
    classifier_intent_for_log = intent

    if intent == "approve":
        state["pending_route"] = "finalize"
    elif intent == "modify":
        new_price = _extract_price(raw_input)
        if new_price and new_price > pending["cost"]:
            new_caption = generate_whatsapp_caption(
                reseller_name, pending["matched_product_name"], pending.get("matched_product_description", ""), new_price
            )
            pending["selling_price"] = new_price
            pending["listing_payload"]["selling_price_inr"] = new_price
            pending["listing_payload"]["whatsapp_caption"] = new_caption.ui_text
            pending["matched_product_name_tts"] = new_caption.product_name_tts
            pending["whatsapp_caption_tts"] = new_caption.tts_text
            PENDING_LISTINGS[pending_key] = pending

            state["reply_text"] = (
                f"Theek hai Didi, price update kar diya. *{pending['matched_product_name']}* ab "
                f"₹{new_price} me list hoga (profit ₹{new_price - pending['cost']}).\n\n{new_caption.ui_text}\n\n"
                f"Kya ab main isey post karun?"
            )
            state["reply_tts_text"] = (
                f"ठीक है दीदी, प्राइस अपडेट कर दिया। {new_caption.product_name_tts} अब "
                f"{new_price} रुपये में लिस्ट होगा, प्रॉफिट {new_price - pending['cost']} रुपये होगा।\n\n{new_caption.tts_text}\n\n"
                f"क्या अब मैं इसे पोस्ट करूं?"
            )
            state["reply_image_url"] = pending["base_image_url"]
            state["detected_intent"] = "CATALOG"
            state["pending_route"] = "price_updated"
        else:
            # Classifier said "modify" but no usable price was found in the text
            # (or it wasn't above cost) - re-ask instead of silently no-op'ing.
            state["reply_text"] = (
                f"Didi, *{pending['matched_product_name']}* ke liye naya price kya rakhun? "
                f"(Abhi ₹{pending['selling_price']} hai, cost ₹{pending['cost']} se zyada hona chahiye)"
            )
            state["reply_tts_text"] = (
                f"दीदी, {pending.get('matched_product_name_tts', pending['matched_product_name'])} के लिए नया प्राइस क्या रखूं? "
                f"अभी {pending['selling_price']} रुपये है, कॉस्ट {pending['cost']} रुपये से ज़्यादा होना चाहिए।"
            )
            state["detected_intent"] = "CATALOG"
            state["pending_route"] = "still_pending"
    else:  # "new_request" - abandon this draft, let the turn flow through normally
        PENDING_LISTINGS.pop(pending_key, None)
        state["pending_route"] = "not_pending"

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Pending Catalog Approval Check",
        "latency_ms": latency,
        "data": {
            "classifier_intent": classifier_intent_for_log,
            "pending_route": state["pending_route"],
            "trigger_text": state.get("raw_input", "")
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "pending_approval_check",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

def route_pending(state: SakhiState) -> str:
    return state.get("pending_route", "not_pending")

_RETURNS_STAGE_LABELS = {
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
_RETURNS_FALLBACK_TEXT = {
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

def _format_alternative_context(pending: Dict[str, Any], stage_label: str) -> str:
    if stage_label in ("B", "C") and pending.get("proposed_alternative"):
        alt = pending["proposed_alternative"]
        return (
            f"ALTERNATIVE_PRODUCT: {alt.get('name')} | Price: {alt.get('suggested_selling_price_inr')} rupaye | "
            f"Sizes: {', '.join(alt.get('sizes') or []) or 'Not specified'} | "
            f"Colors: {', '.join(alt.get('colors') or []) or 'Not specified'}"
        )
    return "ALTERNATIVE_PRODUCT: N/A (not applicable at this stage)."

# ── NODE 1.6: CHECK PENDING RETURN (Returns Retention Funnel) ─────
def check_pending_return(state: SakhiState) -> SakhiState:
    """If a return is in progress for this customer (seeded by
    run_returns_proactive_outreach via the system webhook - see
    /api/v1/system/trigger-return), intercept the turn here and run it
    through the Returns Retention Funnel (Scenarios A-E) instead of normal
    intent detection. Mirrors check_pending_approval's human-in-the-loop
    pattern exactly, keyed the same way, for the same reason: there is no
    LangGraph thread memory, so this dict is the only way to know "this
    customer is mid-return" by the time their next message arrives."""
    t_start = time.time()
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    raw_input = state.get("raw_input", "")

    pending_key = _pending_key(whatsapp_number, active_mode)
    pending = PENDING_RETURNS.get(pending_key)
    if not pending:
        state["pending_return_route"] = "not_pending"
        return state

    original_product = pending.get("original_product")
    terminal = True
    resolution = "refund_forwarded"
    reason = "hard_return"

    if pending.get("stage") == "awaiting_confirmation":
        confirm = classify_exchange_confirmation(raw_input)
        if confirm == "accept":
            stage_label = "E"
            resolution = "exchange_confirmed"
            reason = pending.get("grievance", "exchange")
        else:
            stage_label = "A"
            resolution = "refund_forwarded_after_decline"
            reason = pending.get("grievance", "hard_return")
    else:
        grievance = classify_return_grievance(raw_input, pending.get("product_name", ""))
        reason = grievance
        if grievance == "hard_return":
            stage_label = "A"
        elif grievance == "size_issue":
            alt = None
            if original_product:
                if len(original_product.get("sizes") or []) > 1:
                    alt = original_product
                else:
                    alt = _find_alternative_product(original_product, "different size larger smaller fit")
            if alt:
                stage_label = "B"
                pending["proposed_alternative"] = alt
                pending["stage"] = "awaiting_confirmation"
                pending["grievance"] = "size_issue"
                terminal = False
            else:
                stage_label = "A"
        elif grievance == "color_style_issue":
            alt = None
            if original_product:
                if len(original_product.get("colors") or []) > 1:
                    alt = original_product
                else:
                    alt = _find_alternative_product(original_product, "different color style")
            if alt:
                stage_label = "C"
                pending["proposed_alternative"] = alt
                pending["stage"] = "awaiting_confirmation"
                pending["grievance"] = "color_style_issue"
                terminal = False
            else:
                stage_label = "A"
        else:  # defective
            stage_label = "D"
            pending["proposed_alternative"] = original_product
            pending["stage"] = "awaiting_confirmation"
            pending["grievance"] = "defective"
            terminal = False

    alternative_context = _format_alternative_context(pending, stage_label)
    retention_prompt = RETURNS_RETENTION_SYSTEM_PROMPT.format(
        reseller_name=reseller_name,
        product_name=pending.get("product_name", ""),
        order_id=pending.get("order_id", ""),
        stage_label=_RETURNS_STAGE_LABELS[stage_label],
        user_input=raw_input,
        alternative_context=alternative_context,
    )
    result = generate_structured_with_fallback(retention_prompt, ReturnsAgentResponse)

    fallback_ui, fallback_tts = _RETURNS_FALLBACK_TEXT.get(stage_label, (
        f"Ji, humne {pending.get('product_name', 'is item')} ke liye ek alternative dhoondha hai - kya yeh chalega?",
        f"जी, हमने {pending.get('product_name', 'इस आइटम')} के लिए एक विकल्प ढूंढा है - क्या यह चलेगा?",
    ))
    reply_text = (result.ui_text if result and result.ui_text else fallback_ui)
    reply_tts_text = (result.tts_text if result and result.tts_text else fallback_tts)
    suggests_alternative = result.suggests_alternative if result else (stage_label in ("B", "C"))

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    # Whitelist condition: only ever attach the image when actively naming a
    # specific, really-retrieved alternative (Scenario B/C) - null everywhere
    # else (A, D's first ask, E's closing confirmation), matching the spec.
    state["reply_image_url"] = (
        pending["proposed_alternative"].get("base_image_url")
        if stage_label in ("B", "C") and suggests_alternative and pending.get("proposed_alternative")
        else None
    )
    state["pending_return_route"] = "handled"

    if terminal:
        PENDING_RETURNS.pop(pending_key, None)
        db_client.save_return({
            "reason": reason,
            "resolution": resolution,
            "conversation_log": {
                "order_id": pending.get("order_id"),
                "product_name": pending.get("product_name"),
                "trigger_text": raw_input,
            },
        })
    else:
        PENDING_RETURNS[pending_key] = pending

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "ReturnsAgent",
        "action": f"Returns Retention Funnel - {_RETURNS_STAGE_LABELS[stage_label]}",
        "latency_ms": latency,
        "data": {
            "stage": stage_label,
            "terminal": terminal,
            "trigger_text": raw_input,
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "returns_retention",
        "agent_name": "ReturnsAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

def route_pending_return(state: SakhiState) -> str:
    return state.get("pending_return_route", "not_pending")

# ── NODE 2: INTENT DETECTION ──────────────────────────────────
def detect_intent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    active_mode = state.get("active_mode", "reseller")

    intent = "GENERAL"
    confidence = 1.0
    reason = "Fallback default"

    raw_text = None
    if user_input:
        try:
            if active_mode == "customer":
                prompt = f"""
You are the Orchestrator for Sakhi. You are talking DIRECTLY to an END CUSTOMER (buyer) of a
Meesho reseller - not the reseller herself. Analyze the customer's input and route it to
EXACTLY ONE of the following agents:
1. CUSTOMER: Any product question - size, material, color, delivery, COD, return policy, availability,
   AND any return/exchange/complaint request (the Customer agent has its own deflection rule for these).
   Examples: "kya ye red color me hai?", "size L mil jayega?", "return policy kitne din ki hai?",
   "saree choti pad rahi hai, badalna hai", "mujhe ye wapas karna hai", "exchange option hai?"
2. GENERAL: Greetings, or general chit-chat about what Sakhi can help with.
   Examples: "hello sakhi", "aap kya kar sakti ho?", "thank you"

User Input: "{user_input}"

Output ONLY a valid JSON block of the format:
{{"intent": "CUSTOMER|GENERAL", "confidence": 0.0-1.0, "reason": "one sentence explanation"}}
"""
            else:
                prompt = f"""
You are the Orchestrator for Sakhi, an AI business manager for a Hindi-speaking Meesho reseller.
Analyze the user's input and route it to EXACTLY ONE of the following agents:
1. CATALOG: User wants to list a product, set prices, or create a WhatsApp promotional post.
   Examples: "is saree ko list kar", "add this kurti to my listings for 599", "whatsapp post banao"
2. CUSTOMER: User is relaying a question a buyer asked (e.g., size, material, delivery, cod, return
   policies), AND any return/exchange/complaint the buyer raised (the Customer agent has its own
   deflection rule for these - returns are never processed via chat).
   Examples: "kya ye red color me hai?", "size L mil jayega?", "return policy kitne din ki hai?",
   "customer ko return chahiye", "saree choti pad rahi hai, badalna hai", "exchange option hai?"
3. GROWTH: User is asking for sales advice, performance metrics, weekly profits, or what to sell.
   Examples: "weekly sales dikhao", "is week kya profit hua?", "meri sales kaise badhayein?"
4. GENERAL: Greetings, general chit-chat, or listing capabilities.
   Examples: "hello sakhi", "aap kya kar sakti ho?", "thank you"

User Input: "{user_input}"

Output ONLY a valid JSON block of the format:
{{"intent": "CATALOG|CUSTOMER|GROWTH|GENERAL", "confidence": 0.0-1.0, "reason": "one sentence explanation"}}
"""
            raw_text = generate_with_fallback(prompt)
            if raw_text:
                # Strip markdown block ticks if present
                cleaned = raw_text
                if cleaned.startswith("```json"):
                    cleaned = cleaned.split("```json")[1].split("```")[0].strip()
                elif cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1].split("```")[0].strip()

                data = json.loads(cleaned)
                intent = data.get("intent", "GENERAL").upper()
                confidence = data.get("confidence", 0.9)
                reason = data.get("reason", "")
        except Exception as e:
            logger.error(f"Intent detection parsing failed: {e}. Falling back to keyword matching.")
            raw_text = None

    if not raw_text:
        # Fallback rules based on simple keyword checks - used both when Gemini
        # isn't configured and when every model in the fallback chain failed.
        user_lower = user_input.lower()
        if active_mode == "customer":
            if any(w in user_lower for w in ["return", "wapas", "exchange", "badalna", "choti"]):
                intent = "CUSTOMER"
            elif any(w in user_lower for w in ["size", "fabric", "material", "cod", "delivery", "kya ye", "hai"]):
                intent = "CUSTOMER"
        else:
            if any(w in user_lower for w in ["list", "add", "daal", "saree ko list", "post"]):
                intent = "CATALOG"
            elif any(w in user_lower for w in ["size", "fabric", "material", "cod", "delivery", "kya ye", "hai"]):
                intent = "CUSTOMER"
            elif any(w in user_lower for w in ["sales", "profit", "growth", "coaching", "weekly", "paisa"]):
                intent = "GROWTH"
            elif any(w in user_lower for w in ["return", "wapas", "exchange", "badalna", "choti"]):
                intent = "CUSTOMER"

    # Safety clamp: a customer chatting directly should never trigger reseller-only
    # agents (Catalog listing, Growth analytics) even if the LLM misroutes.
    if active_mode == "customer" and intent in ("CATALOG", "GROWTH"):
        intent = "GENERAL"

    # The Returns Agent is only reachable via the backend system webhook
    # (/api/v1/system/trigger-return) - a customer must never be able to
    # self-initiate a return via chat text. The prompts above no longer offer
    # RETURNS as an option, but this is a hard backstop in case the classifier
    # emits it anyway: reroute to the Customer Agent, which carries a
    # deterministic Return Deflection Rule for exactly this case.
    if intent == "RETURNS":
        intent = "CUSTOMER"

    state["detected_intent"] = intent
    state["intent_confidence"] = confidence
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Intent Routing",
        "latency_ms": latency,
        "data": {
            "detected_intent": intent,
            "confidence": confidence,
            "trigger_text": user_input,
            "reason": reason
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
        "event_type": "intent_detection",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    
    return state

# ── CONDITIONAL ROUTE FUNCTION ────────────────────────────────
def route_decision(state: SakhiState) -> str:
    return state.get("detected_intent", "GENERAL")

def generate_whatsapp_caption(reseller_name: str, product_name: str, product_description: str, selling_price: int) -> CatalogCaptionResponse:
    """Shared by the initial catalog draft and price-renegotiation so the caption
    always reflects the current selling price. Returns the Hinglish caption
    (posted to WhatsApp as-is, and shown in chat), a Devanagari version for when
    this caption is read aloud, and a phonetic Devanagari transliteration of the
    product name alone - CRITICAL TTS RULE: callers that echo the product name
    back in a wrapper sentence (e.g. "Didi, <name> ke liye ... ready hai") must
    use product_name_tts there, never the raw Latin-script name, or Sarvam reads
    it with English stress patterns even inside an otherwise Devanagari sentence."""
    catalog_prompt = f"""
You are 'Catalog Didi', the assistant for a Meesho reseller named {reseller_name}.
Write an engaging, persuasive WhatsApp promotional post for the product below:
Product Name: {product_name}
Material/Details: {product_description}
Selling Price: ₹{selling_price} (Reseller Final Price to customer)

Rules:
- ui_text: Write in warm Hinglish (Hindi written in English alphabets). Include emojis, customer interest hooks, and call-to-actions. Do NOT exceed 5 lines. End strictly with: "Order karne ke liye mujhe WhatsApp message karein! 🌸"
- tts_text: CRITICAL - this must be 100% pure Devanagari script, zero English/Latin words or letters anywhere in it, including the product name (transliterate it into Devanagari too, e.g. "Yellow Chanderi Saree" -> "येलो चंदेरी साड़ी"). This is a strict translation task, not a rewrite - translate ui_text sentence by sentence, leaving nothing in Latin script. No emojis, no markdown symbols (*, _, #), and no "₹" - spell prices as "<number> रुपये" instead.
- Never write "AI Sakhi" in tts_text - spell it phonetically as "ए आई सखी".
- product_name_tts: CRITICAL TTS RULE - transliterate ONLY the product name "{product_name}" phonetically into Devanagari (preserve how it sounds in English, e.g. "Blue Cotton Kurti" -> "ब्लू कॉटन कुर्ती"), NOT a meaning translation.
"""
    result = generate_structured_with_fallback(catalog_prompt, CatalogCaptionResponse)
    if result:
        return result

    fallback = f"🌸 *{product_name}* 🌸\n✨ Bahut hi pyaara fabric aur premium quality!\n💸 Final Price: ₹{selling_price}\nOrder karne ke liye mujhe WhatsApp message karein! 🌸"
    return CatalogCaptionResponse(ui_text=fallback, tts_text=fallback, product_name_tts=product_name)

# ── NODE 3: CATALOG AGENT (Drafts only - human-in-the-loop approval required) ──
def run_catalog_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")

    # 1. Generate text embedding using Gemini
    embedding = []
    if configure_gemini():
        try:
            # Query embedding
            embed_res = genai.embed_content(
                model="models/gemini-embedding-001",
                content=user_input,
                task_type="retrieval_query",
                output_dimensionality=768
            )
            embedding = embed_res['embedding']
        except Exception as e:
            logger.error(f"Embedding generation failed in Catalog Agent: {e}")

    # 2. Query Supabase vector similarity
    similar_skus = db_client.match_products(embedding, threshold=0.2, limit=1)

    matched_product = {}
    selling_price = 0
    cost = 0
    if similar_skus:
        matched_product = similar_skus[0]
        # Auto listing margin logic
        cost = matched_product.get("meesho_cost_inr", 350)
        # Check if user mentioned custom selling price
        suggested_selling_price = matched_product.get("suggested_selling_price_inr", cost + 150)

        # Simple extraction for custom price in text (e.g. "599")
        words = user_input.split()
        selling_price = suggested_selling_price
        for w in words:
            if w.isdigit():
                val = int(w)
                if val > cost:
                    selling_price = val
                    break

        # Real product photo (not AI-generated) - falls back to a seeded placeholder
        # only if this SKU predates the base_image_url column being populated.
        base_image_url = matched_product.get("base_image_url") or \
            f"https://picsum.photos/seed/{matched_product.get('product_id')}/600/400"

        # Prepare draft listing (NOT saved yet - awaiting reseller approval)
        listing_payload = {
            "reseller_id": state.get("reseller_id"),
            "product_id": matched_product.get("product_id"),
            "product_name": matched_product.get("name"),
            "category": matched_product.get("category"),
            "selling_price_inr": selling_price,
            "cost_price_inr": cost,
            "image_url": base_image_url
        }

        # Generate WhatsApp promotion in Hinglish (+ Devanagari for TTS)
        caption_response = generate_whatsapp_caption(
            reseller_name, matched_product.get("name"), matched_product.get("description", ""), selling_price
        )
        listing_payload["whatsapp_caption"] = caption_response.ui_text

        # Human-in-the-loop: hold the draft and wait for explicit reseller approval
        # before it's saved/posted (see check_pending_approval / finalize_catalog_listing).
        PENDING_LISTINGS[_pending_key(whatsapp_number, active_mode)] = {
            "listing_payload": listing_payload,
            "base_image_url": base_image_url,
            "matched_product_name": matched_product.get("name"),
            "matched_product_name_tts": caption_response.product_name_tts,
            # Kept as a sibling key (not inside listing_payload, which gets
            # persisted to Supabase and has no column for this) so the broadcast
            # to the Customer segment can be read aloud in proper Devanagari
            # instead of Sarvam mispronouncing the Hinglish caption.
            "whatsapp_caption_tts": caption_response.tts_text,
            "matched_product_description": matched_product.get("description", ""),
            "selling_price": selling_price,
            "cost": cost,
        }

        reply_text = (
            f"Didi, *{matched_product.get('name')}* ke liye caption aur price ready hai. "
            f"Price: ₹{selling_price} (aapka profit ₹{selling_price - cost} hoga).\n\n"
            f"{caption_response.ui_text}\n\n"
            f"Kya main isey post karun?"
        )
        reply_tts_text = (
            f"दीदी, {caption_response.product_name_tts} के लिए कैप्शन और प्राइस तैयार है। "
            f"प्राइस: {selling_price} रुपये, आपका प्रॉफिट {selling_price - cost} रुपये होगा।\n\n"
            f"{caption_response.tts_text}\n\n"
            f"क्या मैं इसे पोस्ट करूं?"
        )
        state["reply_image_url"] = base_image_url
    else:
        reply_text = "Maaf kijiyega didi, mujhe catalog me is tarah ka koi kapda ya item nahi mila. Kya aap details check karke firse bolengi?"
        reply_tts_text = "माफ़ कीजियेगा दीदी, मुझे कैटलॉग में इस तरह का कोई कपड़ा या आइटम नहीं मिला। क्या आप डिटेल्स चेक करके फिर से बोलेंगी?"

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CatalogAgent",
        "action": "Draft Ready - Awaiting Approval",
        "latency_ms": latency,
        "data": {
            "matched_sku": matched_product.get("product_id", "None"),
            "selling_price": selling_price,
            "margin_profit": (selling_price - cost) if similar_skus else 0,
            "draft_created": bool(similar_skus)
        }
    } 
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "catalog_draft",
        "agent_name": "CatalogAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state


# ── NODE 3.5: FINALIZE CATALOG LISTING (post-approval) ────────
def finalize_catalog_listing(state: SakhiState) -> SakhiState:
    t_start = time.time()
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")
    pending = PENDING_LISTINGS.pop(_pending_key(whatsapp_number, active_mode), None)

    if not pending:
        state["reply_text"] = "Maaf kijiyega Didi, mujhe pichla draft nahi mil raha. Kripya item dobara bataiye."
        state["detected_intent"] = "CATALOG"
        latency = int((time.time() - t_start) * 1000)
        state["trace_logs"].append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": "CatalogAgent",
            "action": "Finalize Listing - No Pending Draft",
            "latency_ms": latency,
            "data": {"error": "no_pending_draft"}
        })
        return state

    listing_payload = pending["listing_payload"]
    base_image_url = pending["base_image_url"]

    ad_image_url = generate_ad_creative(base_image_url, pending["matched_product_name"], pending["selling_price"])
    final_image_url = ad_image_url or base_image_url
    listing_payload["image_url"] = final_image_url

    db_client.save_listing(listing_payload)

    reply_text = (
        f"Ho gaya Didi! *{pending['matched_product_name']}* ₹{pending['selling_price']} me "
        f"live post ho gaya hai (profit ₹{pending['selling_price'] - pending['cost']}).\n\n"
        + ("Maine iske liye ek promotional ad image bhi banayi hai! 🌸" if ad_image_url
           else "Aapki listing product photo ke saath live hai! 🌸")
    )
    reply_tts_text = (
        f"हो गया दीदी! {pending.get('matched_product_name_tts', pending['matched_product_name'])} "
        f"{pending['selling_price']} रुपये में लाइव पोस्ट हो गया है, प्रॉफिट {pending['selling_price'] - pending['cost']} रुपये होगा।\n\n"
        + ("मैंने इसके लिए एक प्रोमोशनल ऐड इमेज भी बनायी है।" if ad_image_url
           else "आपकी लिस्टिंग प्रोडक्ट फोटो के साथ लाइव है।")
    )
    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    state["reply_image_url"] = final_image_url
    state["detected_intent"] = "CATALOG"
    # Flags the API layer to broadcast this post into the Customer segment's
    # chat, simulating the listing reaching buyers.
    state["listing_finalized"] = True
    state["listing_broadcast_caption"] = listing_payload["whatsapp_caption"]
    state["listing_broadcast_caption_tts"] = pending.get("whatsapp_caption_tts", listing_payload["whatsapp_caption"])

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CatalogAgent",
        "action": "Listing Finalized (Post-Approval)",
        "latency_ms": latency,
        "data": {
            "product_name": pending["matched_product_name"],
            "selling_price": pending["selling_price"],
            "margin_profit": pending["selling_price"] - pending["cost"],
            "ad_creative_generated": bool(ad_image_url)
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "catalog_listing_finalized",
        "agent_name": "CatalogAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

CUSTOMER_ZERO_HALLUCINATION_REFUSAL = "Maaf kijiyega, mere pas abhi iski detail nahi hai. Mai Didi se puch kar batati hu."

# RETURN DEFLECTION RULE: the Returns Agent is only reachable via the backend
# system webhook (/api/v1/system/trigger-return), never through user-text
# routing - a customer can never self-initiate a return via chat. Kept as an
# exact deterministic constant (not an LLM-generated string) for the same
# reason CUSTOMER_ZERO_HALLUCINATION_REFUSAL is: zero hallucination risk, and
# it must fire the same way whether or not a matching product happens to turn
# up in RAG.
CUSTOMER_RETURN_DEFLECTION_UI = "Returns aur refunds ke liye, kripya apne Meesho app me 'My Orders' section se return initiate karein. 📦"
CUSTOMER_RETURN_DEFLECTION_TTS = "रिटर्न्स और रिफंड्स के लिए, कृपया अपने मीशो ऐप में 'माय ऑर्डर्स' सेक्शन से रिटर्न इनिशिएट करें."
_RETURN_DEFLECTION_KEYWORDS = ["return", "wapas", "exchange", "badalna", "refund"]

# ── NODE 4: CUSTOMER AGENT (RAG BASED) ────────────────────────
def run_customer_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")

    # RETURN DEFLECTION RULE (checked first, before any RAG/LLM call): if the
    # user is asking to return/exchange an item, do NOT attempt to process it.
    # Politely point them to the Meesho App's own return flow instead. No
    # image is ever attached to this response.
    user_lower = user_input.lower()
    if any(w in user_lower for w in _RETURN_DEFLECTION_KEYWORDS):
        state["reply_text"] = CUSTOMER_RETURN_DEFLECTION_UI
        state["reply_tts_text"] = CUSTOMER_RETURN_DEFLECTION_TTS
        state["reply_image_url"] = None

        latency = int((time.time() - t_start) * 1000)
        log_event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": "CustomerAgent",
            "action": "Return Deflection (chat cannot self-initiate returns)",
            "latency_ms": latency,
            "data": {"trigger_text": user_input}
        }
        state["trace_logs"].append(log_event)
        db_client.log_agent_event({
            "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
            "event_type": "return_deflection",
            "agent_name": "CustomerAgent",
            "latency_ms": latency,
            "payload": log_event["data"]
        })
        return state

    # 1. Generate text embedding using Gemini
    embedding = []
    if configure_gemini():
        try:
            embed_res = genai.embed_content(
                model="models/gemini-embedding-001",
                content=user_input,
                task_type="retrieval_query",
                output_dimensionality=768
            )
            embedding = embed_res['embedding']
        except Exception as e:
            logger.error(f"Embedding generation failed in Customer Agent: {e}")

    # 2. Query Supabase vector similarity matching
    similar_skus = db_client.match_products(embedding, threshold=0.15, limit=2)

    reply_text = ""
    if similar_skus:
        context_str = "\n".join([
            f"Product: {p.get('name')} | Availability: In Stock | Price: {p.get('suggested_selling_price_inr')} rupaye | "
            f"Category: {p.get('category')} | "
            f"Sizes: {', '.join(p.get('sizes') or []) or 'Not specified'} | "
            f"Colors: {', '.join(p.get('colors') or []) or 'Not specified'} | "
            f"Material: {p.get('material') or 'Not specified'} | "
            f"Return window: {p.get('return_window_days')} days | Description: {p.get('description')}"
            for p in similar_skus
        ])

        customer_prompt = f"""
You are 'Customer Didi', a customer query solver for Meesho reseller {reseller_name}.

CRITICAL OVERRIDE - PURCHASE INTENT (check this FIRST, before anything else below):
If the user expresses any desire to buy, purchase, or acquire the item - e.g. "mujhe khareedni hai", "mujhe khareedna hai", "ye pack kar do", "mujhe chahiye", "order karna hai", "price batao aur bhej do", "I want to buy this", "order place karo", "ye chahiye mujhe", "mujhe ye lena hai" - you MUST bypass the strict context rule below entirely. Do NOT reason about whether "how to purchase" is in the context - it never will be, and that is not a reason to refuse. Instead, you MUST output EXACTLY:
ui_text: "Ji zaroor! Maine aapki request note kar li hai. Sunita Didi jald hi aapse final order aur payment ke baare mein baat karengi. 🛍️"
tts_text: "जी ज़रूर! मैंने आपकी रिक्वेस्ट नोट कर ली है. सुनीता दीदी जल्द ही आपसे फाइनल आर्डर और पेमेंट के बारे में बात करेंगी."
answered_from_product_context: false (this is a purchase handoff, not a grounded product answer - no image is shown for order placements, per policy)
The actual transaction is always handed off to the human reseller, never completed by the bot. This override takes priority over every rule below.

Only if the purchase-intent override above does NOT apply, answer the buyer's query based ONLY on the provided context below:

CONTEXT:
{context_str}

USER QUERY:
"{user_input}"

Rules:
- Keep it concise.
- A product appearing in CONTEXT means it EXISTS and IS AVAILABLE - if the customer asks a general availability question ("kya blue kurti available hai?", "kya ye milegi?", "kya hai ye?"), that is answered as long as a matching product is in the context. Do not treat "availability" itself as a missing detail.
- SUCCESS CASE: When you successfully find the product(s) the customer is asking about in the context, you MUST explicitly state the price in both ui_text and tts_text (e.g. "haan, yeh 399 rupaye mein available hai"), and set answered_from_product_context to true.
- CRITICAL FALLBACK RULE: Only use this when the customer asks about a SPECIFIC attribute value that is genuinely absent from context - e.g. they ask for a color/size that is NOT in the product's listed colors/sizes, or a fact nowhere in the description. In that case ui_text MUST be EXACTLY: "{CUSTOMER_ZERO_HALLUCINATION_REFUSAL}" (and tts_text its natural Devanagari equivalent), and you MUST set answered_from_product_context to false. Never guess a specific value not present in context - but do not refuse general availability questions that the context already answers.
- Do NOT make up any details or facts outside the context.
- You must output your response using the provided JSON schema. ui_text must be written in Hinglish (e.g. "Haan didi"). tts_text must be a direct, word-for-word translation of that exact message into Devanagari script (e.g. "हाँ दीदी"). Keep responses strictly under 2 short sentences to ensure fast voice delivery.
- In tts_text: never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी". Never use currency symbols like "₹" - always spell out the price followed by the word "रुपये" (e.g. "799 रुपये" instead of "₹799").
"""
        result = generate_structured_with_fallback(customer_prompt, CustomerAgentResponse)
        reply_text = result.ui_text if result else ""
        reply_tts_text = result.tts_text if result else ""
        answered_from_product_context = result.answered_from_product_context if result else False

        if not reply_text:
            reply_text = "Ji Didi, main check karke batati hu. Custom specifications ke liye hume confirmation leni hogi."
            reply_tts_text = "जी दीदी, मैं चेक करके बताती हूँ। कस्टम स्पेसिफिकेशंस के लिए हमें कन्फर्मेशन लेनी होगी।"
            answered_from_product_context = False

        # Whitelist Condition 2: only attach the product photo when the agent
        # actually answered a grounded product question from context. Default
        # is no image; every other case - fallback/apology, Order Handoff,
        # anything else - is excluded by default, not individually enumerated.
        # Gated on the model's own explicit flag rather than an exact-string
        # match on the reply wording, since the model doesn't always reproduce
        # a mandated string word-for-word (e.g. an attribute-specific apology
        # phrased slightly differently), which would let the image leak through.
        if answered_from_product_context:
            state["reply_image_url"] = similar_skus[0].get("base_image_url")
    else:
        # Default safety fallback - no context at all, so no image either.
        reply_text = CUSTOMER_ZERO_HALLUCINATION_REFUSAL
        reply_tts_text = "माफ़ कीजियेगा, मेरे पास अभी इसकी डिटेल नहीं है। मैं दीदी से पूछ कर बताती हूँ।"

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CustomerAgent",
        "action": "RAG Customer Search",
        "latency_ms": latency,
        "data": {
            "matched_catalog_items_count": len(similar_skus),
            "rag_context_used": bool(similar_skus)
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
        "event_type": "customer_rag",
        "agent_name": "CustomerAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

# ── NODE 5: GROWTH AGENT ──────────────────────────────────────
def run_growth_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    reseller_id = state.get("reseller_id")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    
    # Query sales metrics from Supabase
    analytics = db_client.get_weekly_analytics(reseller_id)
    
    growth_prompt = f"""
You are 'Growth Didi', a business success coach for Meesho reseller {reseller_name}.
Provide sales insights and business advice in warm conversational Hinglish based on their weekly metrics below:

Weekly Sales: ₹{analytics.get('sales_this_week_inr')}
Weekly Profit: ₹{analytics.get('profit_this_week_inr')}
Total Active Listings: {analytics.get('active_listings_count')}
Orders Received: {analytics.get('orders_count')}

Rules:
- Start with a warm greeting (e.g. "Namaste Sunita Didi!").
- Give them simple tips to sell more sarees/kurtis this week (e.g., share on WhatsApp stories in the afternoon, message top 5 repeat buyers).
- Keep it encouraging and under 6 lines.
- You must output your response using the provided JSON schema. ui_text must be written in Hinglish (e.g. "Haan didi"). tts_text must be a direct, word-for-word translation of that exact message into Devanagari script (e.g. "हाँ दीदी").
- In tts_text: never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी". Never use currency symbols like "₹" - always spell out the price followed by the word "रुपये" (e.g. "799 रुपये" instead of "₹799").
"""
    result = generate_structured_with_fallback(growth_prompt, AgentResponse)
    reply_text = result.ui_text if result else ""
    reply_tts_text = result.tts_text if result else ""

    if not reply_text:
        reply_text = f"Namaste {reseller_name} didi! Is hafte aapki sales ₹{analytics.get('sales_this_week_inr')} rahi aur profit ₹{analytics.get('profit_this_week_inr')} hai. Aap WhatsApp stories par kurtis share karke orders badha sakti hain!"
        reply_tts_text = f"नमस्ते {reseller_name} दीदी! इस हफ्ते आपकी सेल्स {analytics.get('sales_this_week_inr')} रुपये रही और प्रॉफिट {analytics.get('profit_this_week_inr')} रुपये है। आप व्हाट्सएप स्टोरीज़ पर कुर्तियां शेयर करके ऑर्डर्स बढ़ा सकती हैं!"

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "GrowthAgent",
        "action": "Sales Coaching & Metrics Analysis",
        "latency_ms": latency,
        "data": {
            "sales_recorded": analytics.get("sales_this_week_inr"),
            "profit_recorded": analytics.get("profit_this_week_inr"),
            "orders_processed": analytics.get("orders_count")
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
        "event_type": "growth_analytics",
        "agent_name": "GrowthAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

# ── SYSTEM-TRIGGERED PROACTIVE RETURN OUTREACH ────────────────
# Not a graph node - this is invoked by a backend system event (e.g. a return
# initiated in the reseller's Meesho seller dashboard), not by a customer
# message, so it deliberately does NOT go through load_memory/detect_intent.
# Faking a synthetic user message and hoping the classifier reliably tags it
# as RETURNS would be fragile; since the system already knows this is a
# returns event by construction, there's nothing to classify.
def run_returns_proactive_outreach(
    whatsapp_number: str, order_id: str, product_name: str, reseller_name: str = "Sunita Didi"
) -> Dict[str, Any]:
    # Seed the Returns Retention Funnel's pending state so the customer's next
    # reply (whichever grievance they describe) is intercepted by
    # check_pending_return instead of falling through to normal intent
    # detection. Keyed the same way as PENDING_LISTINGS/PENDING_RETURNS
    # elsewhere - this system event always targets the Customer segment.
    pending_key = _pending_key(whatsapp_number, "customer")
    PENDING_RETURNS[pending_key] = {
        "order_id": order_id,
        "product_name": product_name,
        "reseller_name": reseller_name,
        "original_product": _lookup_product_by_name(product_name),
        "stage": "awaiting_grievance",
    }

    outreach_prompt = f"""
You are 'Returns Didi', reaching out PROACTIVELY on behalf of Meesho reseller {reseller_name}. The
customer has NOT messaged you - a backend system event just notified you of this:

SYSTEM NOTIFICATION: The customer just initiated a return for Order #{order_id} ({product_name}). You
must immediately reach out to them to ask what the issue is (size, color, defect) and politely offer
to help with an exchange.

Rules:
- Write the first outreach message: mention the order/product, ask what went wrong (fit, color, or defect), and offer an exchange.
- This is the FIRST message in this conversation - you do not have enough information yet to suggest a specific alternative product. Always set suggests_alternative to false here.
- You must output your response using the provided JSON schema. ui_text must be written in Hinglish (e.g. "Haan didi"). tts_text must be a direct, word-for-word translation of that exact message into Devanagari script (e.g. "हाँ दीदी").
- In tts_text: never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी". Never use currency symbols like "₹" - always spell out the price followed by the word "रुपये" (e.g. "799 रुपये" instead of "₹799").
"""
    result = generate_structured_with_fallback(outreach_prompt, ReturnsAgentResponse)
    reply_text = result.ui_text if result else (
        f"Namaste! Mujhe update mila ki aapne {product_name} return ki hai. Kya fit ya color mein koi dikkat aayi? Main ise exchange karwa sakti hu."
    )
    reply_tts_text = result.tts_text if result else (
        f"नमस्ते! मुझे अपडेट मिला की आपने {product_name} रिटर्न की है। क्या फिट या कलर में कोई दिक्कत आयी? मैं इसे एक्सचेंज करवा सकती हूँ।"
    )

    # Whitelist Condition 3: no alternative product has been looked up for this
    # first outreach message, so there is structurally nothing to attach - this
    # holds regardless of what the model sets suggests_alternative to.
    return {
        "reply_text": reply_text,
        "reply_tts_text": reply_tts_text,
        "reply_image_url": None,
    }

# ── NODE 7: GENERAL HANDLER ───────────────────────────────────
def run_general_handler(state: SakhiState) -> SakhiState:
    t_start = time.time()
    reseller_name = state.get("reseller_name", "Sunita Didi")
    user_input = state.get("raw_input", "")
    
    prompt = f"""
You are Sakhi, an AI business co-pilot (called 'Sakhi Didi') for a Meesho reseller named {reseller_name}.
Respond to their greeting/message politely in warm, friendly Hinglish.

User input: "{user_input}"

Capabilities you have:
1. Product Cataloging (saying "Main aapke items lists me add kar sakti hu")
2. Customer Query solver (RAG)
3. Business Growth Coaching
4. Exchange / Return support

Keep your greeting warm, clear, and under 5 lines.
- You must output your response using the provided JSON schema. ui_text must be written in Hinglish (e.g. "Haan didi"). tts_text must be a direct, word-for-word translation of that exact message into Devanagari script (e.g. "हाँ दीदी").
- In tts_text: never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी". Never use currency symbols like "₹" - always spell out the price followed by the word "रुपये" (e.g. "799 रुपये" instead of "₹799").
"""
    result = generate_structured_with_fallback(prompt, AgentResponse)
    reply_text = result.ui_text if result else ""
    reply_tts_text = result.tts_text if result else ""

    if not reply_text:
        reply_text = f"Namaste {reseller_name} didi! Main aapki business Sakhi hu. Main catalog items list kar sakti hu, customer queries solve kar sakti hu, aur returns handle kar sakti hu. Bataiye kya madad karu?"
        reply_tts_text = f"नमस्ते {reseller_name} दीदी! मैं आपकी बिज़नेस सखी हूँ। मैं कैटलॉग आइटम्स लिस्ट कर सकती हूँ, कस्टमर क्वेरीज़ सॉल्व कर सकती हूँ, और रिटर्न्स हैंडल कर सकती हूँ। बताइये क्या मदद करूं?"

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "GeneralAgent",
        "action": "Conversation greeting handler",
        "latency_ms": latency,
        "data": {
            "conversation_status": "interactive"
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
        "event_type": "general_greeting",
        "agent_name": "GeneralAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

# ── NODE 8: ASSEMBLE & SAVE ───────────────────────────────────
def assemble_final_reply(state: SakhiState) -> SakhiState:
    t_start = time.time()
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    
    # Save conversation turns to database for history
    db_client.save_conversation_turn({
        "reseller_id": state.get("reseller_id"),
        "session_id": whatsapp_number,
        "role": "user",
        "content": state.get("raw_input", ""),
        "agent_used": "User"
    })
    
    db_client.save_conversation_turn({
        "reseller_id": state.get("reseller_id"),
        "session_id": whatsapp_number,
        "role": "assistant",
        "content": state.get("reply_text", ""),
        "agent_used": state.get("detected_intent", "GENERAL")
    })
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Assemble Final Response",
        "latency_ms": latency,
        "data": {
            "conversations_archived": True,
            "session_id": whatsapp_number
        }
    }
    state["trace_logs"].append(log_event)
    
    return state

# ── BUILD STATE MACHINE GRAPH ───────────────────────────────
def get_sakhi_agent_graph():
    builder = StateGraph(SakhiState)

    # Define Nodes
    builder.add_node("load_memory", load_memory)
    builder.add_node("check_pending_return", check_pending_return)
    builder.add_node("check_pending_approval", check_pending_approval)
    builder.add_node("detect_intent", detect_intent)
    builder.add_node("catalog_agent", run_catalog_agent)
    builder.add_node("finalize_catalog_listing", finalize_catalog_listing)
    builder.add_node("customer_agent", run_customer_agent)
    builder.add_node("growth_agent", run_growth_agent)
    builder.add_node("general_handler", run_general_handler)
    builder.add_node("assemble_reply", assemble_final_reply)

    # Define Transitions / Edges
    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "check_pending_return")

    # Human-in-the-loop gate: the ONLY way a return can ever start is the
    # backend system webhook (/api/v1/system/trigger-return ->
    # run_returns_proactive_outreach), which seeds PENDING_RETURNS directly -
    # a customer's own chat text can never initiate one (see detect_intent /
    # route_decision below, which has no RETURNS branch at all). But once that
    # webhook has fired, the customer's own free-text replies (describing
    # their grievance, then confirming/declining an exchange) DO need to flow
    # back through this graph turn-by-turn, which is what this gate is for.
    builder.add_conditional_edges(
        "check_pending_return",
        route_pending_return,
        {
            "handled": "assemble_reply",
            "not_pending": "check_pending_approval"
        }
    )

    # Human-in-the-loop gate: a turn with a pending catalog draft is intercepted
    # here (finalize/decline/re-ask) instead of running intent detection again.
    builder.add_conditional_edges(
        "check_pending_approval",
        route_pending,
        {
            "finalize": "finalize_catalog_listing",
            "still_pending": "assemble_reply",
            "price_updated": "assemble_reply",
            "not_pending": "detect_intent"
        }
    )

    # Add conditional router based on classification. RETURNS is deliberately
    # absent here: a customer can never *self-initiate* a return via chat text.
    # Returns only ever start via the system webhook above; once started, the
    # ongoing conversation is handled by check_pending_return, not this router.
    builder.add_conditional_edges(
        "detect_intent",
        route_decision,
        {
            "CATALOG": "catalog_agent",
            "CUSTOMER": "customer_agent",
            "GROWTH": "growth_agent",
            "GENERAL": "general_handler"
        }
    )

    # Wire specialist nodes back to the response assembler
    builder.add_edge("catalog_agent", "assemble_reply")
    builder.add_edge("finalize_catalog_listing", "assemble_reply")
    builder.add_edge("customer_agent", "assemble_reply")
    builder.add_edge("growth_agent", "assemble_reply")
    builder.add_edge("general_handler", "assemble_reply")

    builder.add_edge("assemble_reply", END)

    return builder.compile()

sakhi_orchestrator = get_sakhi_agent_graph()
