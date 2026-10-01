import time

from backend.core.state import SakhiState
from backend.core.gemini_utils import (
    generate_structured_with_fallback,
    AgentResponse,
)
from backend.db.supabase_client import db_client

__all__ = ["run_general_handler"]


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
