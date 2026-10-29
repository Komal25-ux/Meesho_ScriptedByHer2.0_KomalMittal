import time
import logging
from langgraph.graph import StateGraph, END
from backend.db.supabase_client import db_client
from backend.core.gemini_utils import (
    generate_structured_with_fallback,
    CustomerAgentResponse,
    ReturnsAgentResponse,
    IntentRouter,
)
from backend.core.state import SakhiState, _pending_key, conversation_id
from backend.core.constants import (
    CATALOG_SHARE_TRIGGER_RE,
    CUSTOMER_DETAILS_TRIGGER_RE,
    _RETURNS_STAGE_LABELS,
    _RETURNS_FALLBACK_TEXT,
)
from backend.core.routing.approval import classify_approval_intent
from backend.core.pricing import requested_price
from backend.core.prompt_safety import USER_TEXT_RULE, keep_if_prices_grounded, quote_user_text
from backend.core.routing.returns import classify_return_grievance
from backend.core.routing.exchange import classify_exchange_confirmation
from backend.core.routing.triggers import _strip_trigger_prefix
from backend.core.routing.buying_interest import classify_buying_interest
from backend.core.rag.formatting import _format_product_line, _format_alternative_context
from backend.core.rag.retrieval import _find_alternative_product
from backend.core.catalog.captions import generate_whatsapp_caption
from backend.core.agents.growth import run_growth_agent
from backend.core.agents.general import run_general_handler
from backend.core.agents.returns import run_returns_proactive_outreach
from backend.core.agents.catalog import run_catalog_agent
from backend.core.agents.customer import run_customer_agent, _answer_established_item_followup

logger = logging.getLogger("sakhi-backend")

# Shared in-memory session dictionaries (centralized in backend.core.session)
from backend.core.session import (
    PENDING_LISTINGS,
    PENDING_SELECTIONS,
    LAST_VIEWED_PRODUCT,
    FRESH_BROADCAST_LOCK,
    SHOWN_PRODUCT_IDS,
    LAST_REQUESTED_CATEGORY,
    PENDING_RETURNS,
)





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
CUSTOMER JUST SAID:
{user_input}
{user_text_rule}
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
        "session_id": conversation_id(state),
        "event_type": "memory_retrieval",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    
    return state

# ── NODE 1.5: CHECK PENDING CATALOG APPROVAL (Human-in-the-loop) ──

def check_pending_approval(state: SakhiState) -> SakhiState:
    """If a catalog draft is awaiting the reseller's approval, intercept the
    turn here instead of running intent detection, so the graph genuinely
    pauses on the draft until the reseller responds to it. The response is
    classified by an LLM (approve / modify / new_request) rather than keyword
    matching, since phrases like "kar do"/"kardo" show up identically in a
    genuine approval, a price edit, and an unrelated new listing request."""
    t_start = time.time()
    active_mode = state.get("active_mode", "reseller")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    raw_input = state.get("raw_input", "")

    pending_key = _pending_key(conversation_id(state), active_mode)
    pending = PENDING_LISTINGS.get(pending_key)
    if not pending:
        state["pending_route"] = "not_pending"
        return state

    intent = classify_approval_intent(raw_input, pending)
    classifier_intent_for_log = intent

    if intent == "approve":
        state["pending_route"] = "finalize"
    elif intent == "modify":
        new_price = requested_price(raw_input)
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
            state["reply_price"] = new_price
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
        "session_id": conversation_id(state),
        "event_type": "pending_approval_check",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

def route_pending(state: SakhiState) -> str:
    return state.get("pending_route", "not_pending")

# ── NODE 1.7: CHECK PENDING PRODUCT SELECTION (ProductGrid picker) ─
def check_pending_selection(state: SakhiState) -> SakhiState:
    """If a ProductGrid picker was just shown (catalog or customer ambiguous-
    match picker - see run_catalog_agent / run_customer_agent), the next
    message is expected to be one of the displayed product names verbatim,
    since ProductGrid.jsx's onClick sends the tapped option's exact name.
    Routing a bare product name through detect_intent's LLM classifier would
    be a coin flip (no "list"/"return"/etc. verb to key off), so this gate
    resolves which agent originated the picker deterministically from
    PENDING_SELECTIONS - the actual product match is then re-resolved by that
    agent's own exact-name lookup (db_client.get_product_by_name), not here."""
    t_start = time.time()
    active_mode = state.get("active_mode", "reseller")
    raw_input = state.get("raw_input", "")

    pending_key = _pending_key(conversation_id(state), active_mode)
    pending = PENDING_SELECTIONS.get(pending_key)
    if not pending:
        state["pending_selection_route"] = "not_pending"
        return state

    # A tap now arrives wrapped in a Product Card Click trigger phrase (see
    # handleProductCardClick in App.jsx), not the bare product name - strip
    # it back off before the exact-name comparison below. Safe no-op if this
    # message isn't one of those (e.g. the picker was abandoned and the user
    # typed something else instead).
    selection_text = _strip_trigger_prefix(raw_input)
    selected = next(
        (o for o in pending.get("options", []) if (o.get("name") or "").strip().lower() == selection_text.strip().lower()),
        None
    )

    # Whether resolved or not, the picker is consumed - an unrecognized reply
    # abandons it and falls through to normal intent detection instead of
    # silently no-op'ing on a stale selection.
    PENDING_SELECTIONS.pop(pending_key, None)
    state["pending_selection_route"] = pending["agent"] if selected else "not_pending"

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Pending Product Selection Check",
        "latency_ms": latency,
        "data": {
            "resolved": bool(selected),
            "route": state["pending_selection_route"],
            "trigger_text": raw_input
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": conversation_id(state),
        "event_type": "pending_selection_check",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

def route_pending_selection(state: SakhiState) -> str:
    return state.get("pending_selection_route", "not_pending")

# ── NODE 1.75: CHECK FRESH BROADCAST CONTEXT LOCK (Latest Context Lock) ──
def check_fresh_context_lock(state: SakhiState) -> SakhiState:
    """Intercepts exactly the customer's next message after a reseller
    listing was just finalized/broadcast (see FRESH_BROADCAST_LOCK /
    finalize_catalog_listing), so a natural first reaction ("I want to buy",
    "details") binds deterministically to that product instead of running
    through detect_intent's classifier and a fresh vector search - which,
    having no product-specific words of its own, would otherwise commonly
    land on the ambiguous-match picker and show unrelated alternatives
    instead of the item that was just posted.

    One-shot by construction: FRESH_BROADCAST_LOCK is popped unconditionally
    the first time this runs after a broadcast, whether or not the message
    actually turns out to show buying interest - so only the very next
    message ever gets this treatment, exactly as required."""
    t_start = time.time()
    active_mode = state.get("active_mode", "reseller")
    raw_input = state.get("raw_input", "")

    session_key = _pending_key(conversation_id(state), active_mode)
    locked = active_mode == "customer" and FRESH_BROADCAST_LOCK.pop(session_key, False)
    locked_product = LAST_VIEWED_PRODUCT.get(session_key) if locked else None

    if not locked_product or not raw_input or not classify_buying_interest(raw_input, locked_product.get("name", "")):
        state["context_lock_route"] = "not_locked"
        return state

    product_line = _format_product_line(locked_product)
    lock_prompt = f"""# System Persona & Core Objective
You are 'Customer Didi', a polite AI customer support assistant for a Hindi-speaking Meesho reseller. A
product was JUST posted/shared into this customer's chat, and the message below is their very first reply
right after seeing it.

PRODUCT JUST SHARED (the ONLY product relevant to this turn - never consider or search for any other item):
{product_line}

CUSTOMER'S MESSAGE:
{quote_user_text(raw_input)}
{USER_TEXT_RULE}

This message shows buying interest in / a request for details about the product just shared. Respond by:
1. Warmly confirming/describing the item, grounded ONLY in the product above.
2. Stating the price clearly in both ui_text and tts_text.
3. Asking if they'd like you to place the order (e.g. "Kya main aapke liye iska order place kar doon?").

Set answered_from_product_context to true, grounded_via_recent_item to true, return_retention_triggered to
false, and purchase_intent_detected to false - this is high interest, not yet a confirmed order. If they
confirm on their NEXT message, that is handled separately.

# Phonetic & Formatting Guidelines for TTS
- Never use currency symbols like '₹' or 'Rs.' - always spell out the number followed by 'रुपये'.
- Never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी".
- tts_text must be a direct translation of ui_text into pure Devanagari script.
- Keep responses strictly under 2 short sentences.

# Output
You must output your response using the provided JSON schema: ui_text, tts_text, answered_from_product_context,
return_retention_triggered, purchase_intent_detected, grounded_via_recent_item.
"""
    result = keep_if_prices_grounded(
        generate_structured_with_fallback(lock_prompt, CustomerAgentResponse),
        [locked_product.get("suggested_selling_price_inr")],
        where="Latest Context Lock",
    )

    fallback_ui = (
        f"Ji, *{locked_product.get('name')}* abhi hi post hua hai - price ₹{locked_product.get('suggested_selling_price_inr')} hai. "
        f"Kya main aapke liye iska order place kar doon?"
    )
    fallback_tts = (
        f"जी, {locked_product.get('name')} अभी ही पोस्ट हुआ है, प्राइस {locked_product.get('suggested_selling_price_inr')} रुपये है। "
        f"क्या मैं आपके लिए इसका ऑर्डर प्लेस कर दूं?"
    )

    state["reply_text"] = result.ui_text if result and result.ui_text else fallback_ui
    state["reply_tts_text"] = result.tts_text if result and result.tts_text else fallback_tts
    state["reply_image_url"] = locked_product.get("base_image_url")
    state["reply_product_options"] = None
    state["context_lock_route"] = "handled"

    # Keeps the customer grounded on this item for a follow-up confirmation
    # ("haan", "order kar do") exactly like any other Success Case turn.
    LAST_VIEWED_PRODUCT[session_key] = locked_product

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CustomerAgent",
        "action": "Latest Context Lock - Bound to Just-Posted Product",
        "latency_ms": latency,
        "data": {"product_name": locked_product.get("name"), "trigger_text": raw_input}
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": conversation_id(state),
        "event_type": "fresh_context_lock",
        "agent_name": "CustomerAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

def route_fresh_context_lock(state: SakhiState) -> str:
    return state.get("context_lock_route", "not_locked")

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
    active_mode = state.get("active_mode", "reseller")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    raw_input = state.get("raw_input", "")

    pending_key = _pending_key(conversation_id(state), active_mode)
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
        user_input=quote_user_text(raw_input),
        user_text_rule=USER_TEXT_RULE,
        alternative_context=alternative_context,
    )
    result = keep_if_prices_grounded(
        generate_structured_with_fallback(retention_prompt, ReturnsAgentResponse),
        [
            (pending.get("proposed_alternative") or {}).get("suggested_selling_price_inr"),
            (original_product or {}).get("suggested_selling_price_inr"),
        ],
        where="Returns funnel",
    )

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
        # Scenario A (hard return) or E (exchange confirmed) - the conversation
        # is now handed off to the human reseller either way, for the same
        # Notification Bell purchase_intent_detected feeds on the Customer side.
        state["reply_handoff_triggered"] = True
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
        "session_id": conversation_id(state),
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
    """Top-level Orchestrator router. Uses Gemini's structured-output mode
    (generate_structured_with_fallback + IntentRouter, see gemini_utils.py)
    rather than free-text JSON parsing - the model is constrained to emit
    one of exactly five valid route values, so there's no longer a class of
    bug where a plausible-looking-but-malformed response fails json.loads.

    Deliberately no keyword-based emergency fallback: if structured output
    fails to parse (or every model in the fallback chain is unreachable -
    e.g. daily quota exhaustion), this defaults straight to GENERAL. That's
    a real, known trade-off versus the old behaviour (which still routed
    correctly via keyword heuristics during a full LLM outage) - GENERAL
    under a total outage is safe and won't crash the graph, but it does mean
    outage-time messages get a generic reply instead of being routed
    correctly. Accepted as the simpler, more predictable failure mode.
    """
    t_start = time.time()
    user_input = state.get("raw_input", "")
    active_mode = state.get("active_mode", "reseller")

    intent = "GENERAL"

    # Deterministic fast-path for the two Product Card Click triggers (see
    # handleProductCardClick in App.jsx / CATALOG_SHARE_TRIGGER_RE above) -
    # skips the LLM classifier entirely. These exact prefixes are only ever
    # sent by that one click handler, never typed by a user, so there's no
    # real ambiguity for the LLM to resolve, and a fixed rupee/product-name
    # detail-heavy string is exactly the kind of input a semantic classifier
    # can misroute for no benefit.
    if CATALOG_SHARE_TRIGGER_RE.match(user_input):
        intent = "CATALOG"
    elif CUSTOMER_DETAILS_TRIGGER_RE.match(user_input):
        intent = "CUSTOMER"
    elif user_input:
        if active_mode == "customer":
            prompt = f"""You are the Orchestrator for Sakhi. You are talking DIRECTLY to an END CUSTOMER (buyer) of a
Meesho reseller - not the reseller herself.

Evaluate the customer's message below and select the route that matches their underlying semantic
goal. Only CUSTOMER and GENERAL are ever valid choices when talking to a customer directly - a
customer can never trigger CATALOG (listing/pricing is reseller-only) or GROWTH (business metrics are
reseller-only); if the message's goal would otherwise map to one of those, route to GENERAL instead.

Customer's message:
{quote_user_text(user_input)}
{USER_TEXT_RULE}
"""
        else:
            prompt = f"""You are the Orchestrator for Sakhi, an AI business manager for a Hindi-speaking Meesho reseller.

Evaluate the reseller's message below and select the route that matches their underlying semantic goal.

Reseller's message:
{quote_user_text(user_input)}
{USER_TEXT_RULE}
"""
        result = generate_structured_with_fallback(prompt, IntentRouter)
        if result:
            intent = result.route_to

    # Safety clamp: a customer chatting directly should never trigger reseller-only
    # agents (Catalog listing, Growth analytics) even if the LLM misroutes.
    if active_mode == "customer" and intent in ("CATALOG", "GROWTH"):
        intent = "GENERAL"

    # The Returns Agent is only reachable via the backend system webhook
    # (/api/v1/system/trigger-return) - a customer must never be able to
    # self-initiate a return via chat text. IntentRouter's schema still lists
    # RETURNS (see gemini_utils.py) so structured output has a well-formed
    # place to put a return-shaped message if the model reaches for it
    # anyway, but this is the actual enforcement: reroute to the Customer
    # Agent, which carries a deterministic Return Deflection Rule for exactly
    # this case.
    if intent == "RETURNS":
        intent = "CUSTOMER"

    state["detected_intent"] = intent
    state["intent_confidence"] = 1.0

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "Orchestrator",
        "action": "Intent Routing",
        "latency_ms": latency,
        "data": {
            "detected_intent": intent,
            "trigger_text": user_input
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": conversation_id(state),
        "event_type": "intent_detection",
        "agent_name": "Orchestrator",
        "latency_ms": latency,
        "payload": log_event["data"]
    })

    return state

# ── CONDITIONAL ROUTE FUNCTION ────────────────────────────────
def route_decision(state: SakhiState) -> str:
    return state.get("detected_intent", "GENERAL")

# ── NODE 3: CATALOG AGENT (Drafts only - human-in-the-loop approval required) ──
# Extracted to backend.core.agents.catalog.run_catalog_agent



# ── NODE 3.5: FINALIZE CATALOG LISTING (post-approval) ────────
def finalize_catalog_listing(state: SakhiState) -> SakhiState:
    t_start = time.time()
    active_mode = state.get("active_mode", "reseller")
    pending_key = _pending_key(conversation_id(state), active_mode)
    # Read, not popped: the draft is only cleared once the listing is saved,
    # so if the save fails the reseller can simply approve it again.
    pending = PENDING_LISTINGS.get(pending_key)

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

    # The product photo is used as-is - no compositing/AI generation of a
    # price overlay onto the image. The price is rendered by the frontend as
    # a separate PricePatch stitched below the image instead (see reply_price).
    listing_payload["image_url"] = base_image_url

    db_client.save_listing(listing_payload)
    PENDING_LISTINGS.pop(pending_key, None)

    reply_text = (
        f"Ho gaya Didi! *{pending['matched_product_name']}* ₹{pending['selling_price']} me "
        f"live post ho gaya hai (profit ₹{pending['selling_price'] - pending['cost']}).\n\n"
        f"Aapki listing product photo ke saath live hai! 🌸"
    )
    reply_tts_text = (
        f"हो गया दीदी! {pending.get('matched_product_name_tts', pending['matched_product_name'])} "
        f"{pending['selling_price']} रुपये में लाइव पोस्ट हो गया है, प्रॉफिट {pending['selling_price'] - pending['cost']} रुपये होगा।\n\n"
        f"आपकी लिस्टिंग प्रोडक्ट फोटो के साथ लाइव है।"
    )
    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    state["reply_image_url"] = base_image_url
    state["reply_price"] = pending["selling_price"]
    state["detected_intent"] = "CATALOG"
    # Flags the API layer to broadcast this post into the Customer segment's
    # chat, simulating the listing reaching buyers.
    state["listing_finalized"] = True
    state["listing_broadcast_caption"] = listing_payload["whatsapp_caption"]
    state["listing_broadcast_caption_tts"] = pending.get("whatsapp_caption_tts", listing_payload["whatsapp_caption"])
    state["listing_product_name"] = listing_payload["product_name"]
    state["listing_category"] = listing_payload["category"]

    # Seed the CUSTOMER segment's RECENTLY DISCUSSED ITEM (LAST_VIEWED_PRODUCT)
    # with the product that was just posted - broadcastListingToCustomers in
    # App.jsx only inserts a cosmetic chat bubble on the frontend, it never
    # tells the backend a customer has now seen this item. Without this, a
    # customer replying "ye lena hai"/"order kar do" right after the post has
    # no CONTEXT of their own (that phrase has no product-specific words) and
    # no RECENTLY DISCUSSED ITEM either, so Priority 2's condition (b) in
    # run_customer_agent fails and the message falls through to the ambiguous-
    # match picker instead of confirming the order - exactly the "shows more
    # options instead of understanding purchase intent" bug this fixes.
    # suggested_selling_price_inr is overridden to the actual price posted
    # (selling_price), which may differ from the catalog default if the
    # reseller negotiated a custom price before approving.
    matched_product = pending.get("matched_product")
    if matched_product:
        customer_session_key = _pending_key(conversation_id(state), "customer")
        LAST_VIEWED_PRODUCT[customer_session_key] = {
            **matched_product,
            "suggested_selling_price_inr": pending["selling_price"],
        }
        # Arms the Latest Context Lock for exactly the customer's next message
        # - see FRESH_BROADCAST_LOCK's docstring above.
        FRESH_BROADCAST_LOCK[customer_session_key] = True

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CatalogAgent",
        "action": "Listing Finalized (Post-Approval)",
        "latency_ms": latency,
        "data": {
            "product_name": pending["matched_product_name"],
            "selling_price": pending["selling_price"],
            "margin_profit": pending["selling_price"] - pending["cost"]
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": conversation_id(state),
        "event_type": "catalog_listing_finalized",
        "agent_name": "CatalogAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state
# ── NODE 4: CUSTOMER AGENT (RAG BASED) ────────────────────────
# Extracted to backend.core.agents.customer.run_customer_agent
# (_answer_established_item_followup also extracted to backend.core.agents.customer)


# ── NODE 5: GROWTH AGENT ──────────────────────────────────────
# Extracted to backend.core.agents.growth.run_growth_agent



# ── SYSTEM-TRIGGERED PROACTIVE RETURN OUTREACH ────────────────
# Extracted to backend.core.agents.returns.run_returns_proactive_outreach


# ── NODE 7: GENERAL HANDLER ───────────────────────────────────
# Extracted to backend.core.agents.general.run_general_handler



# ── NODE 8: ASSEMBLE & SAVE ───────────────────────────────────
def assemble_final_reply(state: SakhiState) -> SakhiState:
    t_start = time.time()
    
    # Save conversation turns to database for history
    db_client.save_conversation_turn({
        "reseller_id": state.get("reseller_id"),
        "session_id": conversation_id(state),
        "role": "user",
        "content": state.get("raw_input", ""),
        "agent_used": "User"
    })
    
    db_client.save_conversation_turn({
        "reseller_id": state.get("reseller_id"),
        "session_id": conversation_id(state),
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
            "session_id": conversation_id(state)
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
    builder.add_node("check_pending_selection", check_pending_selection)
    builder.add_node("check_fresh_context_lock", check_fresh_context_lock)
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
            "not_pending": "check_pending_selection"
        }
    )

    # Human-in-the-loop gate: a turn replying to a just-shown ProductGrid
    # picker is resolved here deterministically (see check_pending_selection's
    # docstring for why this can't just be left to detect_intent's classifier).
    builder.add_conditional_edges(
        "check_pending_selection",
        route_pending_selection,
        {
            "catalog": "catalog_agent",
            "customer": "customer_agent",
            "not_pending": "check_fresh_context_lock"
        }
    )

    # Latest Context Lock gate: intercepts exactly the customer's next message
    # after a reseller listing was just broadcast (see check_fresh_context_lock's
    # docstring) and binds it deterministically to that product, bypassing
    # detect_intent's classifier and a fresh vector search entirely.
    builder.add_conditional_edges(
        "check_fresh_context_lock",
        route_fresh_context_lock,
        {
            "handled": "assemble_reply",
            "not_locked": "detect_intent"
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
