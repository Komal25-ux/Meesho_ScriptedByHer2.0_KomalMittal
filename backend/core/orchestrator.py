import time
import json
import logging
from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END
import google.generativeai as genai
from backend.config import settings
from backend.db.supabase_client import db_client

logger = logging.getLogger("sakhi-backend")

class SakhiState(TypedDict):
    reseller_id: str
    whatsapp_number: str
    raw_input: str
    input_type: str
    
    # Reseller details
    reseller_name: str
    reseller_location: str
    reseller_language: str
    reseller_dialect: str
    
    # Intent
    detected_intent: str
    intent_confidence: float
    
    # Processing outputs
    reply_text: str
    reply_audio_b64: Optional[str]
    reply_image_url: Optional[str]
    
    # Tracking telemetry for dashboard
    trace_logs: List[Dict[str, Any]]
    
    # DB models context
    context_data: Optional[Dict[str, Any]]

# Configuration helper
def configure_gemini():
    if settings.GEMINI_API_KEY and "YOUR_GEMINI" not in settings.GEMINI_API_KEY:
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            return True
        except Exception as e:
            logger.error(f"Gemini API configuration failed: {e}")
    return False

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

# ── NODE 2: INTENT DETECTION ──────────────────────────────────
def detect_intent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    
    intent = "GENERAL"
    confidence = 1.0
    reason = "Fallback default"

    if configure_gemini() and user_input:
        try:
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
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
            response = model.generate_content(prompt)
            # Parse JSON
            raw_text = response.text.strip()
            # Strip markdown block ticks if present
            if raw_text.startswith("```json"):
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
                
            data = json.loads(raw_text)
            intent = data.get("intent", "GENERAL").upper()
            confidence = data.get("confidence", 0.9)
            reason = data.get("reason", "")
        except Exception as e:
            logger.error(f"Intent detection parsing failed: {e}. Defaulting to GENERAL.")
    else:
        # Mock mode rules based on simple keyword checks
        user_lower = user_input.lower()
        if any(w in user_lower for w in ["list", "add", "daal", "saree ko list", "post"]):
            intent = "CATALOG"
        elif any(w in user_lower for w in ["size", "fabric", "material", "cod", "delivery", "kya ye", "hai"]):
            intent = "CUSTOMER"
        elif any(w in user_lower for w in ["sales", "profit", "growth", "coaching", "weekly", "paisa"]):
            intent = "GROWTH"
        elif any(w in user_lower for w in ["return", "wapas", "exchange", "badalna", "choti"]):
            intent = "RETURNS"

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

# ── NODE 3: CATALOG AGENT ─────────────────────────────────────
def run_catalog_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    
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
        
        # Prepare saving listing
        listing_payload = {
            "reseller_id": state.get("reseller_id"),
            "product_id": matched_product.get("product_id"),
            "product_name": matched_product.get("name"),
            "category": matched_product.get("category"),
            "selling_price_inr": selling_price,
            "cost_price_inr": cost,
            "image_url": f"https://picsum.photos/seed/{matched_product.get('product_id')}/600/400"
        }
        
        # Call Gemini CatalogAgent to write WhatsApp promotion in Hinglish
        whatsapp_caption = ""
        if configure_gemini():
            try:
                model = genai.GenerativeModel(settings.GEMINI_MODEL)
                catalog_prompt = f"""
You are 'Catalog Didi', the assistant for a Meesho reseller named {reseller_name}.
Write an engaging, persuasive WhatsApp promotional post for the product below:
Product Name: {matched_product.get('name')}
Material/Details: {matched_product.get('description')}
Selling Price: ₹{selling_price} (Reseller Final Price to customer)

Rules:
- Write in warm Hinglish (Hindi written in English alphabets).
- Include emojis, customer interest hooks, and call-to-actions.
- Do NOT exceed 5 lines.
- End strictly with: "Order karne ke liye mujhe WhatsApp message karein! 🌸"
"""
                response = model.generate_content(catalog_prompt)
                whatsapp_caption = response.text.strip()
            except Exception as e:
                logger.error(f"Catalog text generation failed: {e}")
                
        if not whatsapp_caption:
            whatsapp_caption = f"🌸 *{matched_product.get('name')}* 🌸\n✨ Bahut hi pyaara fabric aur premium quality!\n💸 Final Price: ₹{selling_price}\nOrder karne ke liye mujhe WhatsApp message karein! 🌸"
            
        listing_payload["whatsapp_caption"] = whatsapp_caption
        # Insert into listings table in Supabase
        db_client.save_listing(listing_payload)
        
        reply_text = f"Didi, maine aapke mock catalog se *{matched_product.get('name')}* dhundh liya hai. Isko ₹{selling_price} me aapki active list me daal diya hai (Aapka profit ₹{selling_price - cost} hoga).\n\nHere is your WhatsApp post description:\n\n{whatsapp_caption}"
        state["reply_image_url"] = listing_payload["image_url"]
    else:
        reply_text = "Maaf kijiyega didi, mujhe catalog me is tarah ka koi kapda ya item nahi mila. Kya aap details check karke firse bolengi?"
        
    state["reply_text"] = reply_text
    
    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CatalogAgent",
        "action": "Product Listing & Promo Generation",
        "latency_ms": latency,
        "data": {
            "matched_sku": matched_product.get("product_id", "None"),
            "selling_price": selling_price if similar_skus else 0,
            "margin_profit": (selling_price - cost) if similar_skus else 0,
            "promo_post_created": bool(similar_skus)
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": state.get("whatsapp_number", "whatsapp:+919876543210"),
        "event_type": "catalog_listing",
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
        
        if configure_gemini():
            try:
                model = genai.GenerativeModel(settings.GEMINI_MODEL)
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
                response = model.generate_content(customer_prompt)
                reply_text = response.text.strip()
            except Exception as e:
                logger.error(f"Customer Agent LLM prompt failed: {e}")
                
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
    
    reply_text = ""
    if configure_gemini():
        try:
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
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
            response = model.generate_content(growth_prompt)
            reply_text = response.text.strip()
        except Exception as e:
            logger.error(f"Growth coach LLM generation failed: {e}")
            
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
    
    reply_text = ""
    if configure_gemini():
        try:
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
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
            response = model.generate_content(returns_prompt)
            reply_text = response.text.strip()
        except Exception as e:
            logger.error(f"Returns LLM generation failed: {e}")
            
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
    
    reply_text = ""
    if configure_gemini():
        try:
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
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
            response = model.generate_content(prompt)
            reply_text = response.text.strip()
        except Exception as e:
            logger.error(f"General agent failed: {e}")
            
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
    builder.add_node("detect_intent", detect_intent)
    builder.add_node("catalog_agent", run_catalog_agent)
    builder.add_node("customer_agent", run_customer_agent)
    builder.add_node("growth_agent", run_growth_agent)
    builder.add_node("returns_agent", run_returns_agent)
    builder.add_node("general_handler", run_general_handler)
    builder.add_node("assemble_reply", assemble_final_reply)
    
    # Define Transitions / Edges
    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "detect_intent")
    
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
    builder.add_edge("customer_agent", "assemble_reply")
    builder.add_edge("growth_agent", "assemble_reply")
    builder.add_edge("returns_agent", "assemble_reply")
    builder.add_edge("general_handler", "assemble_reply")
    
    builder.add_edge("assemble_reply", END)
    
    return builder.compile()

sakhi_orchestrator = get_sakhi_agent_graph()
