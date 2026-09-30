import time

from backend.core.state import SakhiState
from backend.core.gemini_utils import generate_structured_with_fallback, AgentResponse
from backend.core.metrics.sales import _extract_timeframe_days, _aggregate_sales_for_window
from backend.data.mock_sales_data import MOCK_SALES_DATA
from backend.db.supabase_client import db_client

__all__ = ["run_growth_agent"]


def run_growth_agent(state: SakhiState) -> SakhiState:
    t_start = time.time()
    user_input = state.get("raw_input", "")
    reseller_name = state.get("reseller_name", "Sunita Didi")

    requested_days = _extract_timeframe_days(user_input, default_days=7)
    metrics = _aggregate_sales_for_window(MOCK_SALES_DATA, requested_days)

    if metrics["order_count"] == 0:
        data_summary = f"No sales were recorded in the last {requested_days} days."
    else:
        data_summary = (
            f"Timeframe: last {metrics['days']} days\n"
            f"Total Revenue: {metrics['total_revenue']:,} rupaye\n"
            f"Total Profit: {metrics['total_profit']:,} rupaye\n"
            f"Orders in this period: {metrics['order_count']}\n"
            f"Top-Selling Item (by quantity): {metrics['top_selling_item']}\n"
            f"Top Category (by revenue): {metrics['top_category']}"
        )

    growth_prompt = f"""You are Sakhi, an expert AI Business & Growth Coach for Meesho Resellers. Your goal is to analyze the provided sales data summary and present a clear, encouraging, and actionable report to the reseller (Suneeta).

You will receive a pre-calculated data summary for the requested timeframe (e.g. last 10, 15, or 30 days).

DATA SUMMARY (already computed - do not recalculate or invent any numbers, use these exactly):
{data_summary}

Communication Rules:
1. Language: Use friendly, professional Hinglish (Hindi written in the English alphabet).
2. Tone: Encouraging, analytical, and actionable. Address the reseller as "Didi" or "{reseller_name} ji".
3. Structure: Always use emojis and bullet points for readability.
4. Number Formatting (ui_text only): When writing large numbers (revenue, profit, item counts) in ui_text, always use standard comma formatting - e.g. write "54,090", never the raw unformatted "54090". The DATA SUMMARY above already gives you comma-formatted numbers; copy them exactly as-is rather than removing the commas. tts_text follows its own, different number rule instead - see Rule 3 under STRICT TTS CONSTRAINTS below (numbers spelled out fully in Devanagari words, no digits at all).

Required Report Structure:
1. Greeting & Timeframe: Acknowledge the requested time period ({metrics['days']} din).
2. Performance Snapshot: State the Total Revenue and Total Profit clearly.
3. Star Performers: Highlight the top-selling item and the most profitable category based on the data.
4. Growth Advice (Actionable): Give 2 specific tips based on the top performers (e.g. "Since Kurtis are selling fast, you should run a combo offer," or "Focus on sharing more Saree catalogs in WhatsApp groups because they yield higher margins.").

If DATA SUMMARY says no sales were recorded, do not invent a report - acknowledge that gently and encourage the reseller to start promoting, instead of fabricating revenue/profit/top performers.

Example Output (for illustration of tone/structure only - use the real numbers from DATA SUMMARY above, not these):
"Namaste Suneeta ji! 🙏 Aapke pichle 15 din ka business analysis ready hai:

📊 Aapki Sales Report:
- Total Revenue: ₹[Amount]
- Total Profit: ₹[Amount]

🏆 Aapke Top Performers:
- Sabse zyada bikne wala item [Top Item] raha.
- Aapko sabse zyada profit [Top Category] se hua hai.

💡 Sakhi ki Growth Tips:
1. [Tip 1 related to top item] - Ise apne WhatsApp status par aur promote karein!
2. [Tip 2 related to margins] - Festival season aa raha hai, toh in items ke combos banakar share karein.

Kya aap kisi specific category ke baare mein aur details janna chahti hain?"

# STRICT TTS CONSTRAINTS (tts_text)
You are speaking this analysis out loud to the reseller. You must provide a complete, valuable business analysis, but it MUST be highly compressed - this is a SEPARATE, SHORTER piece of writing from ui_text above, not a translation of it. ui_text stays the full, detailed report (markdown, emojis, bullet points, all 4 sections of the Required Report Structure); tts_text is a standalone 3-sentence spoken summary.

Rule 1 - The "Three-Sentence" Architecture: tts_text is strictly limited to a maximum of 3 short sentences, in exactly this structure, so a complete analysis is delivered quickly:
- Sentence 1 (The Metric): State the single most important growth number from DATA SUMMARY (e.g. "Sunita ji, is hafte aapki sales biis pratishat badhi hai!").
- Sentence 2 (The Insight): Explain *why* it happened, grounded only in DATA SUMMARY's top-selling item/category (e.g. "Ye growth sabse zyada cotton saree ki demand ki wajah se hui.").
- Sentence 3 (The Action): Suggest one quick next step, drawn from the same advice given in ui_text (e.g. "Humein aur naye summer designs list karne chahiye.").

Rule 2 - The "One-Breath" Limit: the entire tts_text must be readable in a single breath - under 40 words total. Never use long or complex explanations. Keep it punchy and direct.

Rule 3 - Devanagari Purity: tts_text must be 100% Devanagari script. NO English letters, NO Latin digits, NO emojis, and NO markdown formatting (*, _, #) whatsoever. Spell out every number and percentage in words (e.g. "बीस प्रतिशत", not "20%"; "चौवन हज़ार नब्बे रुपये", not "54,090 रुपये" or "₹54,090"). Never write "AI Sakhi" - always spell it phonetically as "ए आई सखी".

You must output your response using the provided JSON schema: ui_text (full Hinglish report per the Required Report Structure above) and tts_text (the separate, compressed 3-sentence Devanagari summary per the STRICT TTS CONSTRAINTS above).
"""
    result = generate_structured_with_fallback(growth_prompt, AgentResponse)
    reply_text = result.ui_text if result else ""
    reply_tts_text = result.tts_text if result else ""

    if not reply_text:
        if metrics["order_count"] == 0:
            reply_text = f"Namaste {reseller_name} didi! Pichle {metrics['days']} din mein koi sales record nahi hui. Chaliye WhatsApp status aur groups par apne products promote karna shuru karte hain!"
            reply_tts_text = f"नमस्ते {reseller_name} दीदी! पिछले {metrics['days']} दिन में कोई सेल्स रिकॉर्ड नहीं हुई। चलिए व्हाट्सएप स्टेटस और ग्रुप्स पर अपने प्रोडक्ट्स प्रमोट करना शुरू करते हैं!"
        else:
            reply_text = (
                f"Namaste {reseller_name} didi! Pichle {metrics['days']} din ka business analysis: "
                f"Total Revenue ₹{metrics['total_revenue']:,}, Total Profit ₹{metrics['total_profit']:,}. "
                f"Sabse zyada bikne wala item {metrics['top_selling_item']} raha, aur sabse zyada profit "
                f"{metrics['top_category']} category se hua. Ise WhatsApp status par aur promote karein!"
            )
            reply_tts_text = (
                f"नमस्ते {reseller_name} दीदी! पिछले {metrics['days']} दिन का बिज़नेस एनालिसिस: "
                f"टोटल रेवेन्यू {metrics['total_revenue']:,} रुपये, टोटल प्रॉफिट {metrics['total_profit']:,} रुपये। "
                f"सबसे ज़्यादा बिकने वाला आइटम {metrics['top_selling_item']} रहा, और सबसे ज़्यादा प्रॉफिट "
                f"{metrics['top_category']} केटेगरी से हुआ। इसे व्हाट्सएप स्टेटस पर और प्रमोट करें!"
            )

    state["reply_text"] = reply_text
    state["reply_tts_text"] = reply_tts_text

    latency = int((time.time() - t_start) * 1000)
    log_event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": "GrowthAgent",
        "action": "Sales Coaching & Metrics Analysis",
        "latency_ms": latency,
        "data": {
            "requested_days": metrics["days"],
            "total_revenue": metrics["total_revenue"],
            "total_profit": metrics["total_profit"],
            "top_selling_item": metrics["top_selling_item"],
            "top_category": metrics["top_category"],
            "order_count": metrics["order_count"]
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
