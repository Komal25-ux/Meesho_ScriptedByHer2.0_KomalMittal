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
1. CUSTOMER: Any product question - size, material, color, delivery, COD, return policy, availability.
   Examples: "kya ye red color me hai?", "size L mil jayega?", "return policy kitne din ki hai?"
2. RETURNS: Complaint about a product, or a return/exchange request.
   Examples: "saree choti pad rahi hai, badalna hai", "mujhe ye wapas karna hai", "exchange option hai?"
3. GENERAL: Greetings, or general chit-chat about what Sakhi can help with.
   Examples: "hello sakhi", "aap kya kar sakti ho?", "thank you"

User Input: "{user_input}"

Output ONLY a valid JSON block of the format:
{{"intent": "CUSTOMER|RETURNS|GENERAL", "confidence": 0.0-1.0, "reason": "one sentence explanation"}}
"""
            else:
                prompt = f"""
You are the Orchestrator for Sakhi, an AI business manager for a Hindi-speaking Meesho reseller.
Analyze the user's input and route it to EXACTLY ONE of the following agents:
1. CATALOG: User wants to list a product, set prices, or create a WhatsApp promotional post.
   Examples: "is saree ko list kar", "add this kurti to my listings for 599", "whatsapp post banao"
2. CUSTOMER: User is relaying a question a buyer asked (e.g., size, material, delivery, cod, return policies).
   Examples: "kya ye red color me hai?", "size L mil jayega?", "return policy kitne din ki hai?"
3. GROWTH: User is asking for sales advice, performance metrics, weekly profits, or what to sell.
   Examples: "weekly sales dikhao", "is week kya profit hua?", "meri sales kaise badhayein?"
4. RETURNS: User is complaining about a product, wants to return, or wants an exchange.
   Examples: "customer ko return chahiye", "saree choti pad rahi hai, badalna hai", "exchange option hai?"
5. GENERAL: Greetings, general chit-chat, or listing capabilities.
   Examples: "hello sakhi", "aap kya kar sakti ho?", "thank you"

User Input: "{user_input}"

Output ONLY a valid JSON block of the format:
{{"intent": "CATALOG|CUSTOMER|GROWTH|RETURNS|GENERAL", "confidence": 0.0-1.0, "reason": "one sentence explanation"}}
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
                intent = "RETURNS"
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
                intent = "RETURNS"

    # Safety clamp: a customer chatting directly should never trigger reseller-only
    # agents (Catalog listing, Growth analytics) even if the LLM misroutes.
    if active_mode == "customer" and intent in ("CATALOG", "GROWTH"):
        intent = "GENERAL"

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

# ── NODE 4: CUSTOMER AGENT (RAG BASED) ────────────────────────
def run_customer_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")

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

# ── NODE 6: RETURNS AGENT ─────────────────────────────────────
def run_returns_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")

    # Identify return reasons (e.g. "choti pad rahi hai" -> size issue)
    detected_reason = "size_issue" if "choti" in user_input or "size" in user_input else "expectation_mismatch"

    # Insert return event state
    db_client.save_return({
        "reason": detected_reason,
        "resolution": "exchange_offered",
        "conversation_log": {"user_message": user_input}
    })

    # Look for a suitable alternative product to recommend as a replacement.
    # Whitelist Condition 3 for images: only when one is actually found AND
    # the agent explicitly names it as a recommendation (not the general offer).
    alternative_context = "No ALTERNATIVE_PRODUCT found - do not name a specific item, keep the offer general."
    alternative_product = None
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
            logger.error(f"Embedding generation failed in Returns Agent: {e}")

    if embedding:
        alt_matches = db_client.match_products(embedding, threshold=0.15, limit=1)
        if alt_matches:
            alternative_product = alt_matches[0]
            alternative_context = (
                f"ALTERNATIVE_PRODUCT: {alternative_product.get('name')} | "
                f"Price: {alternative_product.get('suggested_selling_price_inr')} rupaye | "
                f"Sizes: {', '.join(alternative_product.get('sizes') or []) or 'Not specified'} | "
                f"Colors: {', '.join(alternative_product.get('colors') or []) or 'Not specified'}"
            )

    returns_prompt = f"""
You are 'Returns Didi', the dispute solver for Meesho reseller {reseller_name}.
The buyer has complained: "{user_input}"
We detected the issue as: {detected_reason}.

{alternative_context}

Task: Respond in warm conversational Hindi/Hinglish.
Rules:
- Sympathize with the size/fit issue.
- Offer them a free size exchange or replacement instead of processing a direct refund.
- Tell them: "Refund ki jagah hum aapko size change karke bhej dete hain, jisse aapko naya stock pasand aaye!"
- WHITELIST - ALTERNATIVE SUGGESTION: Only if an ALTERNATIVE_PRODUCT is given above, you MAY additionally recommend that specific item by name as a replacement. If you do, set suggests_alternative to true. If no ALTERNATIVE_PRODUCT was given, or you choose not to name a specific item, set suggests_alternative to false and keep the offer general.
- You must output your response using the provided JSON schema. ui_text must be written in Hinglish (e.g. "Haan didi"). tts_text must be a direct, word-for-word translation of that exact message into Devanagari script (e.g. "हाँ दीदी"). Keep responses strictly under 2 short sentences to ensure fast voice delivery.
- In tts_text: never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी". Never use currency symbols like "₹" - always spell out the price followed by the word "रुपये" (e.g. "799 रुपये" instead of "₹799").
"""
    result = generate_structured_with_fallback(returns_prompt, ReturnsAgentResponse)
    reply_text = result.ui_text if result else ""
    reply_tts_text = result.tts_text if result else ""
    suggests_alternative = result.suggests_alternative if result else False

    if not reply_text:
        reply_text = "Maaf kijiyega didi customer ko size problem aayi. Hum unko product refund ke badle doosra size free exchange me bhej dete hain!"
        reply_tts_text = "माफ़ कीजियेगा दीदी, कस्टमर को साइज़ प्रॉब्लम आयी। हम उनको प्रोडक्ट रिफंड के बदले दूसरा साइज़ फ्री एक्सचेंज में भेज देते हैं!"
        suggests_alternative = False

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text

    # Whitelist Condition 3: only attach the image when the agent actively
    # named a specific alternative product it actually found via RAG.
    if suggests_alternative and alternative_product:
        state["reply_image_url"] = alternative_product.get("base_image_url")

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "ReturnsAgent",
        "action": "Exchange Offer Routing",
        "latency_ms": latency,
        "data": {
            "dispute_reason": detected_reason,
            "suggested_resolution": "exchange_offered",
            "alternative_suggested": bool(suggests_alternative and alternative_product)
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
        "event_type": "returns_resolution",
        "agent_name": "ReturnsAgent",
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
def run_returns_proactive_outreach(order_id: str, product_name: str, reseller_name: str = "Sunita Didi") -> Dict[str, Any]:
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
    builder.add_node("check_pending_approval", check_pending_approval)
    builder.add_node("detect_intent", detect_intent)
    builder.add_node("catalog_agent", run_catalog_agent)
    builder.add_node("finalize_catalog_listing", finalize_catalog_listing)
    builder.add_node("customer_agent", run_customer_agent)
    builder.add_node("growth_agent", run_growth_agent)
    builder.add_node("returns_agent", run_returns_agent)
    builder.add_node("general_handler", run_general_handler)
    builder.add_node("assemble_reply", assemble_final_reply)

    # Define Transitions / Edges
    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "check_pending_approval")

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

    # Add conditional router based on classification
    builder.add_conditional_edges(
        "detect_intent",
        route_decision,
        {
            "CATALOG": "catalog_agent",
            "CUSTOMER": "customer_agent",
            "GROWTH": "growth_agent",
            "RETURNS": "returns_agent",
            "GENERAL": "general_handler"
        }
    )

    # Wire specialist nodes back to the response assembler
    builder.add_edge("catalog_agent", "assemble_reply")
    builder.add_edge("finalize_catalog_listing", "assemble_reply")
    builder.add_edge("customer_agent", "assemble_reply")
    builder.add_edge("growth_agent", "assemble_reply")
    builder.add_edge("returns_agent", "assemble_reply")
    builder.add_edge("general_handler", "assemble_reply")

    builder.add_edge("assemble_reply", END)

    return builder.compile()

sakhi_orchestrator = get_sakhi_agent_graph()
