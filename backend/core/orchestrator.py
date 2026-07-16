import time
import json
import logging
from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END
import google.generativeai as genai
from backend.config import settings
from backend.db.supabase_client import db_client
from backend.core.gemini_utils import configure_gemini, generate_with_fallback
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

AFFIRMATIVE_KEYWORDS = ["haan", "haa", "ha ", "yes", "kar do", "kardo", "confirm", "post kar", "theek hai", "thik hai", "ok", "okay", "sahi hai", "post karo", "chalo"]
NEGATIVE_KEYWORDS = ["nahi", "no", "cancel", "mat karo", "ruko", "rehne do", "abhi nahi"]

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

    # Set when a catalog listing was just finalized this turn, so the API
    # layer can broadcast the post into the Customer segment's chat.
    listing_finalized: bool
    listing_broadcast_caption: Optional[str]

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
    """If a catalog draft is awaiting the reseller's Haan/Nahi confirmation,
    intercept the turn here instead of running intent detection, so the graph
    genuinely pauses on the draft until the reseller responds to it. A price
    mentioned in the reply (e.g. "Nahi, price 599 kar do") is treated as a
    modification request and takes priority over yes/no keywords, since
    "kar do" and "nahi" can both appear inside a price-change message."""
    t_start = time.time()
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    raw_input = state.get("raw_input", "")
    user_input = raw_input.strip().lower()

    pending_key = _pending_key(whatsapp_number, active_mode)
    pending = PENDING_LISTINGS.get(pending_key)
    if not pending:
        state["pending_route"] = "not_pending"
        return state

    new_price = _extract_price(raw_input)

    if new_price and new_price != pending["selling_price"] and new_price > pending["cost"]:
        new_caption = generate_whatsapp_caption(
            reseller_name, pending["matched_product_name"], pending.get("matched_product_description", ""), new_price
        )
        pending["selling_price"] = new_price
        pending["listing_payload"]["selling_price_inr"] = new_price
        pending["listing_payload"]["whatsapp_caption"] = new_caption
        PENDING_LISTINGS[pending_key] = pending

        state["reply_text"] = (
            f"Theek hai Didi, price update kar diya. *{pending['matched_product_name']}* ab "
            f"₹{new_price} me list hoga (profit ₹{new_price - pending['cost']}).\n\n{new_caption}\n\n"
            f"Kya ab main isey post karun?"
        )
        state["reply_image_url"] = pending["base_image_url"]
        state["detected_intent"] = "CATALOG"
        state["pending_route"] = "price_updated"
    elif any(k in user_input for k in AFFIRMATIVE_KEYWORDS):
        state["pending_route"] = "finalize"
    elif any(k in user_input for k in NEGATIVE_KEYWORDS):
        PENDING_LISTINGS.pop(pending_key, None)
        state["reply_text"] = (
            f"Theek hai Didi, maine *{pending['matched_product_name']}* post nahi kiya. "
            f"Jab ready ho tab naya item batayein."
        )
        state["detected_intent"] = "CATALOG"
        state["pending_route"] = "declined"
    else:
        state["reply_text"] = (
            f"Didi, pehle ye bataiye - *{pending['matched_product_name']}* wali listing "
            f"(₹{pending['selling_price']}) post kar du? Haan ya Nahi bol dijiye. "
            f"Ya price badalna hai to naya price bata dijiye."
        )
        state["detected_intent"] = "CATALOG"
        state["pending_route"] = "still_pending"

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Pending Catalog Approval Check",
        "latency_ms": latency,
        "data": {"pending_route": state["pending_route"], "trigger_text": state.get("raw_input", "")}
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

def generate_whatsapp_caption(reseller_name: str, product_name: str, product_description: str, selling_price: int) -> str:
    """Shared by the initial catalog draft and price-renegotiation so the caption
    always reflects the current selling price."""
    catalog_prompt = f"""
You are 'Catalog Didi', the assistant for a Meesho reseller named {reseller_name}.
Write an engaging, persuasive WhatsApp promotional post for the product below:
Product Name: {product_name}
Material/Details: {product_description}
Selling Price: ₹{selling_price} (Reseller Final Price to customer)

Rules:
- Write in warm Hinglish (Hindi written in English alphabets).
- Include emojis, customer interest hooks, and call-to-actions.
- Do NOT exceed 5 lines.
- End strictly with: "Order karne ke liye mujhe WhatsApp message karein! 🌸"
"""
    caption = generate_with_fallback(catalog_prompt)
    if caption:
        return caption

    return f"🌸 *{product_name}* 🌸\n✨ Bahut hi pyaara fabric aur premium quality!\n💸 Final Price: ₹{selling_price}\nOrder karne ke liye mujhe WhatsApp message karein! 🌸"

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

        # Generate WhatsApp promotion in Hinglish
        whatsapp_caption = generate_whatsapp_caption(
            reseller_name, matched_product.get("name"), matched_product.get("description", ""), selling_price
        )
        listing_payload["whatsapp_caption"] = whatsapp_caption

        # Human-in-the-loop: hold the draft and wait for explicit reseller approval
        # before it's saved/posted (see check_pending_approval / finalize_catalog_listing).
        PENDING_LISTINGS[_pending_key(whatsapp_number, active_mode)] = {
            "listing_payload": listing_payload,
            "base_image_url": base_image_url,
            "matched_product_name": matched_product.get("name"),
            "matched_product_description": matched_product.get("description", ""),
            "selling_price": selling_price,
            "cost": cost,
        }

        reply_text = (
            f"Didi, *{matched_product.get('name')}* ke liye caption aur price ready hai. "
            f"Price: ₹{selling_price} (aapka profit ₹{selling_price - cost} hoga).\n\n"
            f"{whatsapp_caption}\n\n"
            f"Kya main isey post karun?"
        )
        state["reply_image_url"] = base_image_url
    else:
        reply_text = "Maaf kijiyega didi, mujhe catalog me is tarah ka koi kapda ya item nahi mila. Kya aap details check karke firse bolengi?"

    state["reply_text"] = reply_text

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
    state["reply_text"] = reply_text
    state["reply_image_url"] = final_image_url
    state["detected_intent"] = "CATALOG"
    # Flags the API layer to broadcast this post into the Customer segment's
    # chat, simulating the listing reaching buyers.
    state["listing_finalized"] = True
    state["listing_broadcast_caption"] = listing_payload["whatsapp_caption"]

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
            f"Product: {p.get('name')} | Category: {p.get('category')} | "
            f"Sizes: {', '.join(p.get('sizes') or []) or 'Not specified'} | "
            f"Colors: {', '.join(p.get('colors') or []) or 'Not specified'} | "
            f"Material: {p.get('material') or 'Not specified'} | "
            f"Return window: {p.get('return_window_days')} days | Description: {p.get('description')}"
            for p in similar_skus
        ])
        
        customer_prompt = f"""
You are 'Customer Didi', a customer query solver for Meesho reseller {reseller_name}.
Answer the buyer's query based ONLY on the provided context below:

CONTEXT:
{context_str}

USER QUERY:
"{user_input}"

Rules:
- Respond in polite, friendly conversational Hindi (or Hinglish).
- Keep it concise.
- If the context does not contain the answer (e.g. they ask for custom color or size not mentioned), you MUST say EXACTLY: "Maaf kijiyega, mere pas abhi iski detail nahi hai. Mai Didi se puch kar batati hu."
- Do NOT make up any details or facts outside the context.
"""
        reply_text = generate_with_fallback(customer_prompt) or ""

        if not reply_text:
            reply_text = f"Ji Didi, main check karke batati hu. Custom specifications ke liye hume confirmation leni hogi."
    else:
        # Default safety fallback
        reply_text = "Maaf kijiyega, mere pas abhi iski detail nahi hai. Mai Didi se puch kar batati hu."
        
    state["reply_text"] = reply_text
    
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
"""
    reply_text = generate_with_fallback(growth_prompt) or ""
            
    if not reply_text:
        reply_text = f"Namaste {reseller_name} didi! Is hafte aapki sales ₹{analytics.get('sales_this_week_inr')} rahi aur profit ₹{analytics.get('profit_this_week_inr')} hai. Aap WhatsApp stories par kurtis share karke orders badha sakti hain!"
        
    state["reply_text"] = reply_text
    
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
    
    returns_prompt = f"""
You are 'Returns Didi', the dispute solver for Meesho reseller {reseller_name}.
The buyer has complained: "{user_input}"
We detected the issue as: {detected_reason}.

Task: Respond in warm conversational Hindi/Hinglish.
Rules:
- Sympathize with the size/fit issue.
- Offer them a free size exchange or replacement instead of processing a direct refund.
- Tell them: "Refund ki jagah hum aapko size change karke bhej dete hain, jisse aapko naya stock pasand aaye!"
- Do not exceed 4 lines.
"""
    reply_text = generate_with_fallback(returns_prompt) or ""
            
    if not reply_text:
        reply_text = "Maaf kijiyega didi customer ko size problem aayi. Hum unko product refund ke badle doosra size free exchange me bhej dete hain!"
        
    state["reply_text"] = reply_text
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "ReturnsAgent",
        "action": "Exchange Offer Routing",
        "latency_ms": latency,
        "data": {
            "dispute_reason": detected_reason,
            "suggested_resolution": "exchange_offered"
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
"""
    reply_text = generate_with_fallback(prompt) or ""

    if not reply_text:
        reply_text = f"Namaste {reseller_name} didi! Main aapki business Sakhi hu. Main catalog items list kar sakti hu, customer queries solve kar sakti hu, aur returns handle kar sakti hu. Bataiye kya madad karu?"
        
    state["reply_text"] = reply_text
    
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
            "declined": "assemble_reply",
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
