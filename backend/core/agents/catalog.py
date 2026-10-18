import time

from backend.core.state import SakhiState, _pending_key
from backend.core.session import (
    PENDING_LISTINGS,
    PENDING_SELECTIONS,
    LAST_REQUESTED_CATEGORY,
    SHOWN_PRODUCT_IDS,
)
from backend.core.constants import (
    CATALOG_SHARE_TRIGGER_RE,
    REAL_CATEGORIES,
)
from backend.core.routing.triggers import _strip_trigger_prefix
from backend.core.routing.category import extract_category_intent
from backend.core.gemini_utils import embed_content_with_fallback
from backend.core.catalog.captions import generate_whatsapp_caption
from backend.db.supabase_client import db_client


def run_catalog_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")
    whatsapp_number = state.get("whatsapp_number", "whatsapp:+919876543210")
    active_mode = state.get("active_mode", "reseller")

    session_key = _pending_key(whatsapp_number, active_mode)

    # CRITICAL RULE FOR SHARING (see prompt_catalog_agent.md): a Product Card
    # Click in Reseller mode (handleProductCardClick in App.jsx) always sends
    # this exact trigger phrase wrapping the tapped product's name. Strip it
    # back off to the bare name here so the exact-name lookup below matches
    # (and so the reply below can be tailored to explicitly offer "post now
    # or change the price" - see is_share_trigger further down).
    is_share_trigger = bool(CATALOG_SHARE_TRIGGER_RE.match(user_input))
    if is_share_trigger:
        user_input = _strip_trigger_prefix(user_input)

    # Exact-name lookup first - this is how a reseller's tap on a ProductGrid
    # option (see check_pending_selection / ProductGrid.jsx) arrives back
    # here: the frontend sends the option's exact product name as the next
    # message. Resolving it deterministically here avoids re-running the
    # ambiguous vector search below, which could turn up the same cluster of
    # similarly-named SKUs again and show the picker forever.
    exact_match = db_client.get_product_by_name(user_input)

    category_filter = None
    if exact_match:
        similar_skus = [exact_match]
    else:
        # Category-strict pagination - see extract_category_intent's
        # docstring and run_customer_agent's identical use of it.
        category_intent = extract_category_intent(user_input, LAST_REQUESTED_CATEGORY.get(session_key))
        if category_intent in REAL_CATEGORIES:
            category_filter = category_intent
            if category_filter != LAST_REQUESTED_CATEGORY.get(session_key):
                SHOWN_PRODUCT_IDS[session_key] = []
            LAST_REQUESTED_CATEGORY[session_key] = category_filter

        exclude_ids = SHOWN_PRODUCT_IDS.get(session_key, []) if category_filter else []

        # 1. Generate text embedding using Gemini
        embedding = embed_content_with_fallback(user_input, task_type="retrieval_query", output_dimensionality=768)

        # 2. Query Supabase vector similarity - up to 4 candidates, since an
        # ambiguous match now shows a picker instead of silently auto-drafting
        # whichever the search ranked first. Strictly within category_filter
        # and excluding whatever's already been shown in it, if applicable.
        similar_skus = db_client.match_products(
            embedding, threshold=0.2, limit=4,
            category_filter=category_filter, exclude_ids=exclude_ids
        )

        # Category-strict exhaustion - see run_customer_agent's identical
        # check for why this only fires on a genuine "no more options in this
        # category" case, never a coincidental 0-match elsewhere.
        if category_filter and exclude_ids and len(similar_skus) == 0:
            state["reply_text"] = "Maaf kijiyega, is category mein bas itne hi options uplabdh hain."
            state["reply_tts_text"] = "माफ़ कीजियेगा, इस केटेगरी में बस इतने ही ऑप्शन उपलब्ध हैं।"
            state["reply_product_options"] = None
            state["reply_image_url"] = None

            latency = int((time.time() - t_start) * 1000)
            log_event = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "agent": "CatalogAgent",
                "action": "Category Exhausted",
                "latency_ms": latency,
                "data": {"category": category_filter, "already_shown_count": len(exclude_ids)}
            }
            state["trace_logs"].append(log_event)
            db_client.log_agent_event({
                "session_id": whatsapp_number,
                "event_type": "catalog_category_exhausted",
                "agent_name": "CatalogAgent",
                "latency_ms": latency,
                "payload": log_event["data"]
            })
            return state

    # Threshold is 1 (not 2) when category_filter is active - see
    # run_customer_agent's identical picker_threshold for the reasoning.
    picker_threshold = 1 if category_filter else 2
    if len(similar_skus) >= picker_threshold:
        # Ambiguous - pause the auto-draft and ask the reseller which SKU they
        # mean instead. Nothing is written to PENDING_LISTINGS yet; the
        # selection is resolved by check_pending_selection on the next turn.
        options = [
            {
                "name": p.get("name"),
                "price": p.get("suggested_selling_price_inr") or max(p.get("meesho_cost_inr", 350) + 150, int(p.get("meesho_cost_inr", 350) / 0.7)),
                "base_image_url": p.get("base_image_url") or f"https://picsum.photos/seed/{p.get('product_id')}/600/400"
            }
            for p in similar_skus[:4]
        ]
        PENDING_SELECTIONS[session_key] = {
            "agent": "catalog",
            "options": options,
        }
        if category_filter:
            shown = SHOWN_PRODUCT_IDS.setdefault(session_key, [])
            shown.extend(p.get("product_id") for p in similar_skus[:4] if p.get("product_id"))
        state["reply_text"] = "Didi, mujhe catalog me kuch milte-julte options mile hain. Kripya bataiye kaunsa item list karna hai:"
        state["reply_tts_text"] = "दीदी, मुझे कैटलॉग में कुछ मिलते-जुलते ऑप्शन मिले हैं। कृपया बताइये कौनसा आइटम लिस्ट करना है।"
        state["reply_product_options"] = options
        state["reply_image_url"] = None

        latency = int((time.time() - t_start) * 1000)
        log_event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": "CatalogAgent",
            "action": "Multiple SKU Matches - Awaiting Selection",
            "latency_ms": latency,
            "data": {"matched_catalog_items_count": len(similar_skus), "category_filter": category_filter}
        }
        state["trace_logs"].append(log_event)
        db_client.log_agent_event({
            "session_id": whatsapp_number,
            "event_type": "catalog_selection_prompt",
            "agent_name": "CatalogAgent",
            "latency_ms": latency,
            "payload": log_event["data"]
        })
        return state

    matched_product = {}
    selling_price = 0
    cost = 0
    if similar_skus:
        matched_product = similar_skus[0]
        # Auto listing margin logic
        cost = matched_product.get("meesho_cost_inr", 350)
        # Check if user mentioned custom selling price
        suggested_selling_price = matched_product.get("suggested_selling_price_inr") or max(cost + 150, int(cost / 0.7))

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
        PENDING_LISTINGS[session_key] = {
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
            # Full product dict, kept for finalize_catalog_listing to seed the
            # CUSTOMER segment's LAST_VIEWED_PRODUCT once this listing actually
            # goes live - see the comment there for why this is necessary.
            "matched_product": matched_product,
        }

        if is_share_trigger:
            # Group Sharing flow (see prompt_catalog_agent.md) - explicitly
            # acknowledges the selected item, states the suggested price
            # (Python-sourced cost + margin, never invented), and asks
            # permission to post OR offers a price change in the same
            # message. "Yes"/a new price on the next turn is resolved by the
            # existing check_pending_approval/_extract_price flow - no
            # separate state machine needed for this trigger.
            reply_text = (
                f"Zaroor Didi! *{matched_product.get('name')}* ki cost price ₹{cost} hai. "
                f"Hum isko WhatsApp group mein ₹{selling_price} mein post kar sakte hain "
                f"(aapka profit ₹{selling_price - cost} hoga).\n\n"
                f"{caption_response.ui_text}\n\n"
                f"Kya main isko post kar doon, ya aap price change karna chahengi?"
            )
            reply_tts_text = (
                f"ज़रूर दीदी! {caption_response.product_name_tts} की कॉस्ट प्राइस {cost} रुपये है। "
                f"हम इसको व्हाट्सएप ग्रुप में {selling_price} रुपये में पोस्ट कर सकते हैं, "
                f"आपका प्रॉफिट {selling_price - cost} रुपये होगा।\n\n"
                f"{caption_response.tts_text}\n\n"
                f"क्या मैं इसको पोस्ट कर दूं, या आप प्राइस चेंज करना चाहेंगी?"
            )
        else:
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
        state["reply_price"] = selling_price
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
