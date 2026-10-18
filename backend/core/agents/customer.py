import time
from typing import Dict, Any

from backend.core.state import SakhiState, _pending_key
from backend.core.session import (
    LAST_VIEWED_PRODUCT,
    LAST_REQUESTED_CATEGORY,
    SHOWN_PRODUCT_IDS,
    PENDING_SELECTIONS,
    PENDING_RETURNS,
)
from backend.core.constants import (
    CUSTOMER_DETAILS_TRIGGER_RE,
    REAL_CATEGORIES,
    CUSTOMER_ZERO_HALLUCINATION_REFUSAL,
    CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS,
    DRILL_DOWN_CTA,
    DRILL_DOWN_CTA_TTS,
)
from backend.core.routing.triggers import _strip_trigger_prefix
from backend.core.routing.category import extract_category_intent
from backend.core.routing.attribute_followup import classify_attribute_followup
from backend.core.rag.formatting import _format_product_line
from backend.core.gemini_utils import (
    generate_structured_with_fallback,
    embed_content_with_fallback,
    CustomerAgentResponse,
)
from backend.db.supabase_client import db_client


def _answer_established_item_followup(
    state: SakhiState, product: Dict[str, Any], user_input: str,
    session_key: str, whatsapp_number: str, t_start: float
) -> SakhiState:
    """Deterministic Drill-Down State reply (see classify_attribute_followup's
    call site in run_customer_agent) - grounds strictly on `product` (the
    established RECENTLY DISCUSSED ITEM), never runs a fresh vector search,
    never attaches an image (Action A - media suppressed regardless of
    whether it would've been correct), and always closes with the mandated
    sale-prompt CTA (Action B), enforced in Python as a hard guarantee, not
    left to the model alone."""
    product_line = _format_product_line(product)
    prompt = f"""# System Persona & Core Objective
You are 'Customer Didi', a polite AI customer support assistant for a Hindi-speaking Meesho reseller. The
customer is asking a follow-up question about a product they were already just discussing.

ESTABLISHED PRODUCT (the ONLY product relevant to this turn - do not consider or search for any other item):
{product_line}

CUSTOMER'S FOLLOW-UP QUESTION: "{user_input}"

Answer their specific question directly and warmly, grounded ONLY in the product above (e.g. if they asked
about size, clearly state the available sizes; if a specific attribute is genuinely absent from the product
data above, say so rather than guessing). Do not re-describe the whole product unless asked. Your reply
MUST end with the exact closing question: "{DRILL_DOWN_CTA}"

# Phonetic & Formatting Guidelines for TTS
- Never use currency symbols like '₹' or 'Rs.' - always spell out the number followed by 'रुपये'.
- Never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी".
- tts_text must be a direct translation of ui_text into pure Devanagari script, and must end with the
  Devanagari equivalent of the closing question: "{DRILL_DOWN_CTA_TTS}"
- Keep responses strictly under 2 short sentences plus the mandated closing question.

# Output
Set answered_from_product_context to true, grounded_via_recent_item to true, return_retention_triggered to
false, and purchase_intent_detected to false.
You must output your response using the provided JSON schema: ui_text, tts_text, answered_from_product_context,
return_retention_triggered, purchase_intent_detected, grounded_via_recent_item.
"""
    result = generate_structured_with_fallback(prompt, CustomerAgentResponse)

    sizes = ', '.join(product.get('sizes') or []) or 'abhi update nahi hui hai'
    fallback_ui = f"Iske available sizes hain: {sizes}. {DRILL_DOWN_CTA}"
    fallback_tts = f"इसके उपलब्ध साइज़ हैं: {sizes}. {DRILL_DOWN_CTA_TTS}"

    reply_text = result.ui_text if result and result.ui_text else fallback_ui
    reply_tts_text = result.tts_text if result and result.tts_text else fallback_tts

    if DRILL_DOWN_CTA.lower() not in reply_text.lower():
        reply_text = f"{reply_text.rstrip()} {DRILL_DOWN_CTA}"
    if DRILL_DOWN_CTA_TTS not in reply_tts_text:
        reply_tts_text = f"{reply_tts_text.rstrip()} {DRILL_DOWN_CTA_TTS}"

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text
    state["reply_image_url"] = None
    state["reply_product_options"] = None

    # Keeps the item grounded for a further follow-up or a confirmation next turn.
    LAST_VIEWED_PRODUCT[session_key] = product

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CustomerAgent",
        "action": "Drill-Down Follow-up on Established Item",
        "latency_ms": latency,
        "data": {"product_name": product.get("name"), "trigger_text": user_input}
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "customer_drill_down_followup",
        "agent_name": "CustomerAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state

# ── NODE 4: CUSTOMER AGENT (RAG BASED) ────────────────────────
def run_customer_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")

    session_key = _pending_key(whatsapp_number, active_mode)

    # CRITICAL RULE FOR ITEM CLICKS (see prompt_customer_agent.md): a Product
    # Card Click in Customer mode (handleProductCardClick in App.jsx) always
    # sends this exact trigger phrase wrapping the tapped product's name.
    # Strip it back off to the bare name so the exact-name lookup below
    # matches; is_details_trigger is passed into the prompt further down as
    # an explicit PRODUCT_CARD_CLICK signal (Priority 1.5) so the model
    # treats this as high purchase interest rather than a generic query.
    is_details_trigger = bool(CUSTOMER_DETAILS_TRIGGER_RE.match(user_input))
    if is_details_trigger:
        user_input = _strip_trigger_prefix(user_input)

    # Exact-name lookup first - this is how a customer's tap on a ProductGrid
    # option (see check_pending_selection / ProductGrid.jsx) arrives back
    # here: the frontend sends the option's exact product name as the next
    # message. Resolved deterministically instead of re-running the ambiguous
    # vector search below, which could resurface the same cluster of
    # similarly-named SKUs and show the picker again.
    exact_match = db_client.get_product_by_name(user_input)

    # Deterministic Drill-Down short-circuit: decided BEFORE category
    # extraction / vector search even run, so a noisy or misclassified
    # CONTEXT never gets the chance to derail an attribute follow-up ("size
    # kya hai", "colors kya hain") about the item the customer is ALREADY
    # looking at into the ambiguous-match picker - see
    # classify_attribute_followup's docstring for why this can't just be left
    # to the main prompt's Rule 3b. Skipped for a fresh exact-name match or a
    # Product Card Click - those are legitimate new/first identifications,
    # not a follow-up on an established item.
    if not exact_match and not is_details_trigger:
        early_recent_product = LAST_VIEWED_PRODUCT.get(session_key)
        if early_recent_product and classify_attribute_followup(user_input, early_recent_product.get("name", "")):
            return _answer_established_item_followup(
                state, early_recent_product, user_input, session_key, whatsapp_number, t_start
            )

    category_filter = None
    if exact_match:
        similar_skus = [exact_match]
    else:
        # Category-strict pagination: figure out which real category (if
        # any) this message is scoped to - see extract_category_intent's
        # docstring for why this is a CONTEXT-narrowing hint only, never a
        # routing decision, so it can never collide with Priority 1/2 below.
        category_intent = extract_category_intent(user_input, LAST_REQUESTED_CATEGORY.get(session_key))
        if category_intent in REAL_CATEGORIES:
            category_filter = category_intent
            if category_filter != LAST_REQUESTED_CATEGORY.get(session_key):
                # Genuinely new category - old exclusions no longer apply.
                SHOWN_PRODUCT_IDS[session_key] = []
            LAST_REQUESTED_CATEGORY[session_key] = category_filter

        exclude_ids = SHOWN_PRODUCT_IDS.get(session_key, []) if category_filter else []

        # 1. Generate text embedding using Gemini
        embedding = embed_content_with_fallback(user_input, task_type="retrieval_query", output_dimensionality=768)

        # 2. Query Supabase vector similarity matching - up to 4 candidates,
        # strictly within category_filter (if the message was scoped to one)
        # and excluding whatever this session was already shown in that
        # category (pagination). NOTE: ambiguity among these is NOT decided
        # here anymore - see below. A phrase like "mujhe ye khareedna hai" or
        # "saree wapas karni hai" has no specific product attributes in it,
        # so a naive match-count check right here would misfire on generic
        # purchase/return phrases just as easily as on a genuine multi-SKU
        # product query, hijacking the turn before Priority 1/2 below ever
        # get a chance to run - that was the actual cause of the "purchase
        # intent loops back into product suggestions" bug. Priority 1/2 must
        # always be checked FIRST, via the same LLM call that would otherwise
        # attempt a grounded answer; only if none of them apply AND the model
        # itself couldn't confidently ground an answer do we fall back to
        # showing a picker (further down).
        similar_skus = db_client.match_products(
            embedding, threshold=0.15, limit=4,
            category_filter=category_filter, exclude_ids=exclude_ids
        )

        # Category-strict exhaustion: only short-circuits here when we were
        # explicitly continuing a category-scoped browse (exclude_ids
        # non-empty means this session had already been shown something in
        # this category) and filtering left nothing - a genuine "no more
        # options" case. A coincidental 0-match on an unrelated message
        # (return/purchase/etc.) never reaches this, since exclude_ids is
        # only ever populated once a category browse has actually started.
        if category_filter and exclude_ids and len(similar_skus) == 0:
            state["reply_text"] = "Maaf kijiyega, is category mein bas itne hi options uplabdh hain."
            state["reply_tts_text"] = "माफ़ कीजियेगा, इस केटेगरी में बस इतने ही ऑप्शन उपलब्ध हैं।"
            state["reply_product_options"] = None
            state["reply_image_url"] = None

            latency = int((time.time() - t_start) * 1000)
            log_event = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "agent": "CustomerAgent",
                "action": "Category Exhausted",
                "latency_ms": latency,
                "data": {"category": category_filter, "already_shown_count": len(exclude_ids)}
            }
            state["trace_logs"].append(log_event)
            db_client.log_agent_event({
                "session_id": whatsapp_number,
                "event_type": "customer_category_exhausted",
                "agent_name": "CustomerAgent",
                "latency_ms": latency,
                "payload": log_event["data"]
            })
            return state

    reseller_id = state.get("reseller_id", "")
    for p in similar_skus:
        p_id = p.get("product_id")
        is_listed = False
        if reseller_id and p_id:
            is_listed = db_client.is_product_listed(reseller_id, p_id)
        p["is_unlisted"] = not is_listed
        if not is_listed:
            cost = p.get("meesho_cost_inr", 350)
            price_30_margin = int(cost / 0.7)
            price_min_profit = cost + 150
            dynamic_price = max(price_min_profit, price_30_margin)
            p["suggested_selling_price_inr"] = dynamic_price

    recent_product = LAST_VIEWED_PRODUCT.get(session_key)
    if recent_product:
        rp_id = recent_product.get("product_id")
        is_rp_listed = False
        if reseller_id and rp_id:
            is_rp_listed = db_client.is_product_listed(reseller_id, rp_id)
        recent_product["is_unlisted"] = not is_rp_listed
        if not is_rp_listed:
            cost = recent_product.get("meesho_cost_inr", 350)
            price_30_margin = int(cost / 0.7)
            price_min_profit = cost + 150
            dynamic_price = max(price_min_profit, price_30_margin)
            recent_product["suggested_selling_price_inr"] = dynamic_price

    context_str = "\n".join(_format_product_line(p) for p in similar_skus) if similar_skus \
        else "No matching product found in the catalog for this query."

    # Last item this session was actually grounded on (see LAST_VIEWED_PRODUCT
    # docstring above) - the referent for a bare confirmation like "isko order
    # kar do" that doesn't repeat the product name, since that phrase's own
    # vector search below has nothing product-specific to match against.
    recent_product = LAST_VIEWED_PRODUCT.get(session_key)
    recent_context_str = _format_product_line(recent_product) if recent_product else "None."

    # Single system prompt covering every turn - Priority 1 (Return Retention
    # Hook) and Priority 2 (Purchase Confirmation Intent) are checked by the
    # model itself, in sequence, before the strict RAG rules apply. NOTE:
    # image_url is deliberately NOT part of CustomerAgentResponse (see
    # gemini_utils.py) - reproducing a CDN URL byte-for-byte in LLM JSON is a
    # real fidelity risk, so this prompt tells the model to leave image
    # handling to the system rather than asking it to output a URL it cannot
    # reliably reproduce.
    #
    # Priority 2 deliberately treats "exactly one product in CONTEXT" as its
    # proxy for "a specific item is established," not real cross-turn memory -
    # this app has none (every /chat/send call is a stateless graph
    # invocation; see PENDING_LISTINGS/PENDING_RETURNS/PENDING_SELECTIONS for
    # how the few things that DO need turn-to-turn continuity are handled
    # instead). A generic phrase like "saree leni hai" matches loosely against
    # several catalog items (ambiguous CONTEXT) just like a genuine purchase
    # confirmation with no real referent would; the proxy is what lets the
    # model tell those apart without needing conversation history it doesn't
    # have.
    customer_prompt = f"""# System Persona & Core Objective
You are 'Customer Didi', a polite and friendly AI customer support assistant representing a Hindi-speaking Meesho reseller named {reseller_name}. Your primary job is to answer buyer queries regarding product availability, sizes, colors, material, and pricing.
You must prioritize customer retention, zero-hallucination factual grounding, and professional transaction handoffs.

# Priority Routing Override Rules (Checked in Sequence)

## Priority 1: Return Retention Hook
Trigger: the user asks about returning an item, getting a refund, exchanging a product, or indicates dissatisfaction with size/fit/quality (e.g. "mujhe return chahiye", "refund milega?", "saree wapas karni hai", "exchange kaise hoga?", "size chota hai").
Action: you must immediately attempt to save the sale by asking for the specific reason for the return (Size, Color, or Defect) so we can offer an exchange.
You MUST output EXACTLY:
ui_text: "Oh! Maaf kijiyega ki product aapki ummeedon par khara nahi utra. Kya main jaan sakti hu ki issue kya hai? Size, color ya fitting mein koi dikkat aayi? Main turant isko exchange karwa sakti hu. 🔄"
tts_text: "ओह! माफ़ कीजियेगा की प्रोडक्ट आपकी उम्मीदों पर खरा नहीं उतरा. क्या मैं जान सकती हूँ की इशू क्या है? साइज, कलर या फिटिंग में कोई दिक्कत आयी? मैं तुरंत इसको एक्सचेंज करवा सकती हूँ."
answered_from_product_context: false
return_retention_triggered: true
purchase_intent_detected: false
grounded_via_recent_item: false

## Priority 1.5: Product Card Click (High Purchase Interest)
Trigger: PRODUCT_CARD_CLICK below is true. This means the customer tapped a specific product card to see its details - a strong, explicit signal of high interest, distinct from both a generic browsing question and an actual purchase confirmation (that's Priority 2, which this is NOT - it's a details request, not a confirmed order yet).
Action:
1. Give a short, warm Hinglish description of the item, grounded ONLY in CONTEXT below (same zero-hallucination rule as Product Query Handling).
2. State the final price clearly, in both ui_text and tts_text.
3. Explicitly ask if they want to place the order (e.g. "Kya main aapke liye iska order place kar doon?").
Set answered_from_product_context to true, return_retention_triggered to false, purchase_intent_detected to false, and grounded_via_recent_item to false (this is a fresh identification via the card tapped, not a recall of an older item) - this turn is high interest, not yet a confirmed order. If the customer confirms on their NEXT message (e.g. "haan", "order kar do"), Priority 2 below handles that turn using RECENTLY DISCUSSED ITEM (this item will already be remembered there once this turn completes).

PRODUCT_CARD_CLICK: {'true' if is_details_trigger else 'false'}

## Priority 2: Purchase Confirmation Intent
Not every mention of buying is a completed decision - you must strictly separate EXPLORATORY interest from an actual CONFIRMATION. Getting this wrong in either direction is a real bug: treating exploration as confirmation skips showing the customer any products; treating confirmation as exploration loops them back into search when they already decided.

CRITICAL RULE: do NOT set purchase_intent_detected to true if the user is making a general inquiry about a category or type of product (e.g. "saree leni hai", "kurti chahiye", "kuch dikhao", "kya options hain", "mujhe ek achi saree chahiye"). This is EXPLORATORY - no specific item has been pinned down yet, only a desire to be shown some. Skip this priority entirely and fall through to Product Query Handling below, where you retrieve and describe matching products from CONTEXT as usual.

WATCH FOR THIS TRAP: "leni"/"lena" are just gender-agreement forms of the same verb ("to take"), so an EXPLORATORY phrase and a CHECKOUT phrase can look almost identical on the surface - the deciding signal is what comes immediately before "leni/lena hai", not the verb itself:
- "saree leni hai" (a CATEGORY NOUN before it) = EXPLORATORY. purchase_intent_detected: false.
- "ye lena hai" or "ye wali" (a DEMONSTRATIVE PRONOUN before it, pointing at something already shown or discussed - see condition (b) below) = CHECKOUT, same as "order kar do"/"pack kar do".
Apply the same noun-vs-pronoun test to any other confirmatory-sounding verb, not just this pair.

ONLY set purchase_intent_detected to true if BOTH of these hold:
(a) The wording confirms/finalizes a purchase decision, on one specific already-identified item rather than a category. This does NOT require an explicit pronoun ("isko"/"ye"/"yehi") - a bare confirmation like "order kar do", "pack kar do", "confirm kar do", or "final karo" with no other product/category mentioned is just as much a confirmation as "ye wali pack kardo", "haan ye done hai", "iska order kardo", "isse le lo", "yehi confirm kardo", "ye lena hai", "isko pack kar do", "ye order karna hai". The only thing that makes it EXPLORATORY instead (see the CRITICAL RULE / trap above) is naming/asking about a category or a new item.
(b) EXACTLY ONE product is established as the referent for words like "isko"/"ye"/"yehi"/"isse". This holds if EITHER: CONTEXT below (this message's own product matches) contains exactly one product; OR CONTEXT is empty/ambiguous but RECENTLY DISCUSSED ITEM below is present AND this message does not itself name or ask about some other specific product or category (a bare confirmation phrase like "isko order kar do" has no product-specific words in it, so its own CONTEXT will usually be empty or noisy - RECENTLY DISCUSSED ITEM is what resolves "isko" in that case). If neither holds, nothing specific has actually been pinned down, so confirming an order is logically impossible no matter how confirmatory the wording sounds - condition (b) fails and purchase_intent_detected MUST stay false. Concretely: if "ye lena hai" arrives out of nowhere - CONTEXT empty/ambiguous AND RECENTLY DISCUSSED ITEM is "None." - do not invent a referent for "ye". Condition (b) fails; fall through to the clarification branch below instead of confirming.

RECENTLY DISCUSSED ITEM (the last product this customer was specifically shown/answered about, from an earlier message - "None." if nothing yet):
{recent_context_str}

If (a) holds but (b) fails (confirmatory wording, but CONTEXT does not resolve to exactly one item): do not guess which item they mean and do not hand off an order. Ask for clarification instead.
You MUST output EXACTLY:
ui_text: "Aap kaunsi wali confirm karna chahte hain?"
tts_text: "आप कौनसी वाली कन्फर्म करना चाहते हैं?"
answered_from_product_context: false
return_retention_triggered: false
purchase_intent_detected: false
grounded_via_recent_item: false

If (a) AND (b) both hold: you cannot complete financial transactions. Do NOT describe or search for the product again. Bypass the RAG context rules below entirely and hand off the order to the human reseller.
You MUST output EXACTLY:
ui_text: "Ji zaroor! Aapka order confirm karne ke liye main reseller ko notify kar rahi hoon. Sunita Didi jald hi aapse sampark karengi. 🛍️"
tts_text: "जी ज़रूर! आपका ऑर्डर कन्फर्म करने के लिए मैं रीसेलर को नोटिफाई कर रही हूँ. सुनीता दीदी जल्द ही आपसे संपर्क करेंगी."
answered_from_product_context: false
return_retention_triggered: false
purchase_intent_detected: true
grounded_via_recent_item: false

# Product Query Handling (Strict RAG Rules)
Only if Priority 1 and Priority 2 above do NOT apply, answer based ONLY on the provided context below.

CONTEXT:
{context_str}

USER QUERY:
"{user_input}"

1. Factual Constraints: Do not invent attributes outside CONTEXT or RECENTLY DISCUSSED ITEM (whichever grounds the answer per the rules below). A product appearing there means it EXISTS and IS AVAILABLE - a general availability question ("kya ye milegi?") is answered as long as a matching product is available; do not treat availability itself as a missing detail.
2. Browsing Case (General/Exploratory Query, 2+ Candidates): If the query is a general browsing request rather than a question about one specific, already-identified item (e.g. "saree dikhao", "kuch achi kurti dikhao", "kya options hain") AND CONTEXT lists 2 or more candidate products, do NOT try to describe or compare all of them yourself in ui_text/tts_text - even though you technically could. The system will show them to the customer as a visual picker instead, which they can tap directly; a wall of text listing multiple names/prices is worse UX than that picker and defeats its purpose. In this case ui_text/tts_text can be a brief one-line acknowledgement (it will likely be replaced by the picker anyway). Set answered_from_product_context to false, return_retention_triggered to false, purchase_intent_detected to false, and grounded_via_recent_item to false. This does NOT apply when rule 3b below resolves the query to RECENTLY DISCUSSED ITEM instead - a pronoun referring to a known item is never a fresh browsing request, no matter how many loose/unrelated matches this message's own CONTEXT happens to contain.
3. Success Case (Single Specific Item): Only when CONTEXT effectively resolves to ONE relevant item (either exactly one product in CONTEXT, or the query clearly asks about one specific item even if a second loosely-related product is also present in CONTEXT) do you answer directly. Answer warmly. You MUST state the price in both ui_text and tts_text (e.g. "haan, yeh 399 rupaye mein available hai"). Set answered_from_product_context to true, return_retention_triggered to false, purchase_intent_detected to false, and grounded_via_recent_item to false (this message's own CONTEXT is what resolved it, not a recall of an older item).
3b. Pronoun Fallback to Recently Discussed Item: The query may refer to a product using only a pronoun/demonstrative and no product-specific words at all (e.g. "iska size kya hai?", "ismein aur colors hain?", "is it available in blue?", "what sizes are available in this?"). A query like that has nothing for its own CONTEXT above to match against, so CONTEXT will usually be empty or a noisy, unrelated set of loose matches - the same situation Priority 2's condition (b) above already handles for purchase confirmations. Apply the identical resolution here: if RECENTLY DISCUSSED ITEM above is present (it says "None." when it is not), treat IT as the grounding item for this Success Case and answer from its attributes, instead of falling through to the Browsing Case or refusing for lack of context. Do NOT trigger a broad catalog search or picker just because this message's own CONTEXT was empty/ambiguous - a known pronoun referring to an already-shared/posted item always takes priority over that. This only applies while the pronoun genuinely points at RECENTLY DISCUSSED ITEM; if the query names a different/new product or category, resolve normally instead. This is a DEEP-DIVE / DRILL-DOWN turn on an already-selected item, not a fresh identification - this message's own CONTEXT above may be noisy/unrelated (it was not a real match, just low-threshold search noise), so end ui_text with the exact closing question "kya isse order kar dun?" (and tts_text with its Devanagari equivalent "क्या इसे ऑर्डर कर दूं?") to prompt the sale. Set answered_from_product_context to true, return_retention_triggered to false, purchase_intent_detected to false, and grounded_via_recent_item to true - this last flag tells the system this message's own CONTEXT must not be trusted for anything (including the reply's image), only RECENTLY DISCUSSED ITEM's own image is safe.
4. Strict Fallback Refusal (Details Missing): If asked for a specific attribute value genuinely absent from both CONTEXT and RECENTLY DISCUSSED ITEM (whichever grounded the answer), do NOT guess. ui_text MUST be EXACTLY: "{CUSTOMER_ZERO_HALLUCINATION_REFUSAL}" and tts_text MUST be EXACTLY: "{CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS}". Set answered_from_product_context to false, return_retention_triggered to false, purchase_intent_detected to false, and grounded_via_recent_item to false.

# Phonetic & Formatting Guidelines for TTS
- Never use currency symbols like '₹' or 'Rs.' - always spell out the number followed by 'रुपये' (e.g. "799 रुपये").
- Never write "AI Sakhi" - always spell it phonetically in Devanagari as "ए आई सखी".
- tts_text must be a direct, word-for-word translation of ui_text into pure Devanagari script.
- Keep responses strictly under 2 short sentences, except where an EXACT string is mandated above - reproduce that verbatim.

# Output
Image handling is managed entirely by the system based on your answered_from_product_context and grounded_via_recent_item flags - do not attempt to output an image URL yourself, it is not part of your output schema.
You must output your response using the provided JSON schema: ui_text, tts_text, answered_from_product_context, return_retention_triggered, purchase_intent_detected, grounded_via_recent_item.
"""
    result = generate_structured_with_fallback(customer_prompt, CustomerAgentResponse)
    reply_text = result.ui_text if result and result.ui_text else CUSTOMER_ZERO_HALLUCINATION_REFUSAL
    reply_tts_text = result.tts_text if result and result.tts_text else CUSTOMER_ZERO_HALLUCINATION_REFUSAL_TTS
    answered_from_product_context = result.answered_from_product_context if result else False
    return_retention_triggered = result.return_retention_triggered if result else False
    purchase_intent_detected = result.purchase_intent_detected if result else False
    grounded_via_recent_item = result.grounded_via_recent_item if result else False

    # Priority 2 fired - stop here. No RAG image, no ambiguous-match picker,
    # no further product search: the customer already said what they want,
    # so re-asking or re-suggesting products here is exactly the loop this
    # branch exists to prevent.
    if purchase_intent_detected:
        state["reply_text"] = reply_text
        state["reply_tts_text"] = reply_tts_text
        state["reply_image_url"] = None
        state["reply_product_options"] = None

        # The confirmed item must be the one the customer was actually just
        # shown/discussing, not whatever this turn's own vector search
        # happened to turn up - a bare confirmation phrase like "order kar
        # do" or "ye lena hai" has no product-specific words in it, so any
        # single same-turn match against it is name/description noise from a
        # low similarity threshold, not a real reference. RECENTLY DISCUSSED
        # ITEM (recent_product) is the one deterministic source of truth for
        # what was actually established as the referent (seeded by a details
        # view or a listing broadcast - see finalize_catalog_listing), so it
        # must win whenever it's present; only fall back to this turn's own
        # single match when there is no established item to confirm against.
        # Getting this wrong is exactly the "Notification Bell shows a
        # different product than what the customer actually confirmed" bug.
        confirmed_product = recent_product if recent_product else (similar_skus[0] if len(similar_skus) == 1 else None)

        state["reply_purchase_intent_detected"] = True

        # Strict State Synchronization: the reseller notification is never
        # built from confirmed_product / session state directly past this
        # point - it is read back from the row db_client.save_order() actually
        # persisted (echoed verbatim in mock mode; the real inserted row in
        # Supabase mode). This is the definitive Order record - see the
        # product-snapshot columns added to the orders table in
        # supabase_schema.sql - so a later mismatch between "what the customer
        # confirmed" and "what the reseller was told" is structurally
        # impossible, not just unlikely: both come from the exact same row.
        if confirmed_product:
            reseller_id = state.get("reseller_id")
            unit_price = confirmed_product.get("suggested_selling_price_inr")
            listing_id = db_client.get_listing_id(reseller_id, confirmed_product.get("product_id")) if reseller_id else None
            order_data = {
                "reseller_id": reseller_id,
                "listing_id": listing_id,
                "buyer_whatsapp": whatsapp_number,
                "quantity": 1,
                "total_amount_inr": unit_price,
                "status": "confirmed",
                "product_id": confirmed_product.get("product_id"),
                "product_name": confirmed_product.get("name"),
                "unit_price_inr": unit_price,
                "available_sizes": confirmed_product.get("sizes") or [],
                "available_colors": confirmed_product.get("colors") or [],
            }
            saved_order = db_client.save_order(order_data)
            # Falls back to the exact same Python-resolved values already in
            # order_data whenever the DB write didn't go through (save_order
            # returns {} on any insert error - e.g. a live schema drift where
            # the orders table is missing a column this code expects, which
            # is a real failure mode this app hit: the table must be migrated
            # separately via supabase_schema.sql, editing that file alone
            # does not apply it). Python already knows exactly what was
            # confirmed regardless of whether the write succeeded - a
            # transient/config write failure must never blank out the
            # reseller notification; it only means this order has no durable
            # order_id to reference later. dict.get(key, default) here relies
            # on the KEY being absent (not just falsy) on failure, which
            # holds: saved_order is {} in that case, so every key is absent.
            state["reply_order_id"] = saved_order.get("id")
            state["reply_confirmed_product_name"] = saved_order.get("product_name", order_data["product_name"])
            state["reply_confirmed_product_price"] = saved_order.get("unit_price_inr", order_data["unit_price_inr"])
            state["reply_confirmed_product_is_unlisted"] = not saved_order.get("listing_id", listing_id)
        else:
            # Condition (b) still failed despite purchase_intent_detected somehow
            # coming back true (a model inconsistency, not a case Python can
            # resolve) - nothing to persist; notify with no product identity
            # rather than guessing one.
            state["reply_order_id"] = None
            state["reply_confirmed_product_name"] = None
            state["reply_confirmed_product_price"] = None
            state["reply_confirmed_product_is_unlisted"] = False

        # Order is placed - clear the remembered item so a stray later
        # message doesn't "confirm" the same purchase a second time.
        LAST_VIEWED_PRODUCT.pop(session_key, None)

        latency = int((time.time() - t_start) * 1000)
        log_event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": "CustomerAgent",
            "action": "order_placed",
            "latency_ms": latency,
            "data": {
                "action": "order_placed",
                "notified": "reseller",
                "order_id": state.get("reply_order_id"),
                "product_name": state.get("reply_confirmed_product_name")
            }
        }
        state["trace_logs"].append(log_event)
        db_client.log_agent_event({
            "session_id": whatsapp_number,
            "event_type": "customer_purchase_intent",
            "agent_name": "CustomerAgent",
            "latency_ms": latency,
            "payload": log_event["data"]
        })
        return state

    # Ambiguous product query: Priority 1/2 didn't apply, and the model itself
    # couldn't confidently ground an answer from multiple candidate SKUs -
    # hand the customer a picker instead of guessing (or refusing) among them.
    # Checked AFTER the LLM call (unlike the old match-count-only check) so a
    # generic purchase/return phrase that happens to loosely match several
    # SKUs never reaches here - Priority 1/2 above already claimed it. (Note:
    # purchase_intent_detected already returned early above; return_retention_
    # triggered is guarded here explicitly since it falls through to the
    # PENDING_RETURNS handoff further below, not an early return.)
    #
    # Threshold is 1 (not 2) when category_filter is active: a category-
    # scoped "show more" that has exactly one item left should still render
    # as a picker (consistent, tappable pagination UI), not silently switch
    # into the single-item prose-answer flow below, which exists for a
    # different case (a specific already-identified item).
    picker_threshold = 1 if category_filter else 2
    if not return_retention_triggered and not answered_from_product_context and len(similar_skus) >= picker_threshold:
        options = [
            {
                "name": p.get("name"),
                "price": p.get("suggested_selling_price_inr"),
                "base_image_url": p.get("base_image_url") or f"https://picsum.photos/seed/{p.get('product_id')}/600/400"
            }
            for p in similar_skus[:4]
        ]
        PENDING_SELECTIONS[session_key] = {
            "agent": "customer",
            "options": options,
        }
        if category_filter:
            # Pagination memory: never show these same items again for the
            # rest of this category's browse (see SHOWN_PRODUCT_IDS docstring).
            shown = SHOWN_PRODUCT_IDS.setdefault(session_key, [])
            shown.extend(p.get("product_id") for p in similar_skus[:4] if p.get("product_id"))
        state["reply_text"] = "Ji, mujhe kuch milte-julte options mile hain. Kripya bataiye aapko kis item ke baare mein jaanna hai:"
        state["reply_tts_text"] = "जी, मुझे कुछ मिलते-जुलते ऑप्शन मिले हैं। कृपया बताइये आपको किस आइटम के बारे में जानना है।"
        state["reply_product_options"] = options
        state["reply_image_url"] = None

        latency = int((time.time() - t_start) * 1000)
        log_event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": "CustomerAgent",
            "action": "Multiple SKU Matches - Awaiting Selection",
            "latency_ms": latency,
            "data": {"matched_catalog_items_count": len(similar_skus), "category_filter": category_filter}
        }
        state["trace_logs"].append(log_event)
        db_client.log_agent_event({
            "session_id": whatsapp_number,
            "event_type": "customer_selection_prompt",
            "agent_name": "CustomerAgent",
            "latency_ms": latency,
            "payload": log_event["data"]
        })
        return state

    # Drill-Down State: rule 3b resolved this turn from RECENTLY DISCUSSED ITEM,
    # not this message's own CONTEXT - a pronoun-only follow-up ("iska size kya
    # hai?") has no product-specific words in it, so any single-item match
    # similar_skus turns up against it is name/description noise from the low
    # similarity threshold, not a real reference. Trusting that noise for the
    # image (the old behaviour below) is exactly the "correct text, unrelated/
    # hallucinated image" bug - so a drill-down turn never attaches ANY image,
    # and always closes with the mandated sale-prompt CTA instead.
    is_drill_down_followup = answered_from_product_context and grounded_via_recent_item
    if is_drill_down_followup:
        if DRILL_DOWN_CTA.lower() not in reply_text.lower():
            reply_text = f"{reply_text.rstrip()} {DRILL_DOWN_CTA}"
        if DRILL_DOWN_CTA_TTS not in reply_tts_text:
            reply_tts_text = f"{reply_tts_text.rstrip()} {DRILL_DOWN_CTA_TTS}"

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text

    # Whichever item actually grounded the answer - this message's own single
    # match, or (rule 3b above) the carried-over RECENTLY DISCUSSED ITEM when
    # a pronoun-only query ("iska size kya hai?") left similar_skus empty/
    # noisy. Mirrors the same fallback Priority 2 already uses for
    # confirmed_product above. On a drill-down turn, similar_skus is never
    # trusted at all (see is_drill_down_followup above) - only recent_product is.
    grounding_product = recent_product if is_drill_down_followup else (similar_skus[0] if similar_skus else recent_product)

    # Whitelist Condition 2: only attach the product photo when the agent
    # actually answered a grounded product question from context. Default is
    # no image; every other case - fallback/apology, Purchase Handoff, Return
    # Retention Hook, greetings, Drill-Down State (Action A - media suppressed
    # by spec regardless of whether the image would've been correct), anything
    # else - is excluded by default, not individually enumerated. Gated on the
    # model's own explicit flag rather than the real base_image_url ever
    # passing through the model itself.
    state["reply_image_url"] = (
        grounding_product.get("base_image_url")
        if answered_from_product_context and grounding_product and not is_drill_down_followup
        else None
    )

    # Remember this as the item a future bare confirmation ("isko order kar
    # do") should resolve to - see LAST_VIEWED_PRODUCT docstring above.
    if answered_from_product_context and grounding_product:
        LAST_VIEWED_PRODUCT[_pending_key(whatsapp_number, active_mode)] = grounding_product

    # TASK 2 - Returns Handoff: if the Return Retention Hook fired this turn,
    # seed the same PENDING_RETURNS state the system webhook uses (see
    # check_pending_return / run_returns_proactive_outreach) so the customer's
    # NEXT reply is intercepted by that gate and routed through the already-
    # built Returns Retention Funnel (Scenarios A-E) instead of staying stuck
    # in the Customer Agent loop. No new graph edges are needed for this - the
    # graph already routes to check_pending_return on every turn before
    # detect_intent runs; seeding this dict is what makes it fire next turn.
    if return_retention_triggered:
        matched_product = similar_skus[0] if similar_skus else None
        PENDING_RETURNS[_pending_key(whatsapp_number, active_mode)] = {
            "order_id": None,
            "product_name": matched_product.get("name") if matched_product else "the product",
            "reseller_name": reseller_name,
            "original_product": matched_product,
            "stage": "awaiting_grievance",
        }

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "CustomerAgent",
        "action": "RAG Customer Search",
        "latency_ms": latency,
        "data": {
            "matched_catalog_items_count": len(similar_skus),
            "rag_context_used": bool(similar_skus),
            "return_retention_triggered": return_retention_triggered
        }
    }
    state["trace_logs"].append(log_event)
    db_client.log_agent_event({
        "session_id": whatsapp_number,
        "event_type": "customer_rag",
        "agent_name": "CustomerAgent",
        "latency_ms": latency,
        "payload": log_event["data"]
    })
    return state
