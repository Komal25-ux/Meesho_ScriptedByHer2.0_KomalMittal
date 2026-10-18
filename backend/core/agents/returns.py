from typing import Dict, Any

from backend.core.session import PENDING_RETURNS
from backend.core.state import _pending_key
from backend.core.rag.retrieval import _lookup_product_by_name
from backend.core.gemini_utils import (
    generate_structured_with_fallback,
    ReturnsAgentResponse,
)


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
