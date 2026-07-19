# Growth Agent ('Sakhi' Business Coach) Prompt Specification

This file documents the prompt specification for the **Growth Agent** (`run_growth_agent` in `backend/core/orchestrator.py`). Like `prompt_customer_agent.md`, this is the source-of-truth design doc - the actual prompt embedded in `orchestrator.py` is this text with the DATA SUMMARY, timeframe, and reseller name substituted in via an f-string.

---

## 1. Why the LLM Never Sees Raw Transactions

The Growth Agent does **not** hand the model `MOCK_SALES_DATA` and ask it to summarize/compute anything. `run_growth_agent` filters and aggregates the data in Python first (`_extract_timeframe_days` + `_aggregate_sales_for_window`), and the model only ever receives the **already-correct** pre-calculated numbers as a DATA SUMMARY block. This is the same zero-hallucination-grounding principle used everywhere else in this file (RAG context for the Customer Agent, retrieved product data for Returns) - arithmetic and data retrieval are Python's job; turning correct numbers into a warm, structured Hinglish report is the model's job. The model is explicitly instructed not to recalculate or invent any numbers.

## 2. Timeframe Extraction

`_extract_timeframe_days(user_input, default_days=7)` pulls a day-count out of phrasing like *"15 din ka data dikhao"* or *"pichle 30 days ka analysis"* via a regex (`\b(\d{1,3})\s*(?:din|dino|days?)\b`), not an LLM call - the same reasoning as `_extract_price` elsewhere in `orchestrator.py`: pulling one number out of text is a task regex handles reliably and near-instantly, so spending a full model round-trip on it would only add latency for no accuracy benefit. If no day-count is found in the message, it defaults to **7 days**.

## 3. Data Aggregation

`_aggregate_sales_for_window` filters `backend/data/mock_sales_data.py` (a direct Python port of `frontend/src/data/mockSalesData.js` - see that file's own docstring for why the two must stay in sync) to the last N calendar days ending at the dataset's own latest date (derived from the data, not hardcoded, so this stays correct if the dataset's range ever changes), then computes:
- **total_revenue**: sum of `revenue` across the filtered transactions.
- **total_profit**: sum of `profit` across the filtered transactions.
- **top_selling_item**: the `productName` with the highest summed `quantity`.
- **top_category**: the `category` with the highest summed `revenue`.

If the filtered window has zero transactions, the model is told explicitly ("No sales were recorded in the last N days") rather than being handed empty/zero fields to describe as if they were a real (if quiet) business result - see the "no sales" rule in the prompt below.

## 4. System Prompt

```text
You are Sakhi, an expert AI Business & Growth Coach for Meesho Resellers. Your goal is to analyze the provided sales data summary and present a clear, encouraging, and actionable report to the reseller (Suneeta).

You will receive a pre-calculated data summary for the requested timeframe (e.g., last 10, 15, or 30 days).

Communication Rules:
1. Language: Use friendly, professional Hinglish (Hindi written in the English alphabet).
2. Tone: Encouraging, analytical, and actionable. Address the reseller as "Didi" or "Suneeta ji".
3. Structure: Always use emojis and bullet points for readability.

Required Report Structure:
1. Greeting & Timeframe: Acknowledge the requested time period.
2. Performance Snapshot: State the Total Revenue and Total Profit clearly.
3. Star Performers: Highlight the top-selling item and the most profitable category based on the data.
4. Growth Advice (Actionable): Give 2 specific tips based on the top performers. (e.g., "Since Kurtis are selling fast, you should run a combo offer," or "Focus on sharing more Saree catalogs in WhatsApp groups because they yield higher margins.")

Example Output:
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
```

### Additions beyond the base text
Two things are layered on top of the text above when it's actually assembled in `orchestrator.py`, both necessary for the agent to function correctly rather than being purely cosmetic:
- **DATA SUMMARY injection**: the Python-computed metrics (§3) are inserted before the Communication Rules, with an explicit instruction not to recalculate or invent numbers - this is what makes the "pre-calculated data summary" the base text refers to actually exist in the prompt the model receives.
- **No-sales rule**: if DATA SUMMARY reports zero transactions in the window, the model is told to acknowledge that gently and encourage promotion instead of fabricating a report - the base text's structure otherwise implicitly assumes there's always something to report.
- **Standard dual-output/TTS rules**: the same phonetic/formatting rules every other agent's prompt in this file carries (spell "Sakhi" phonetically, no `₹` symbol in `tts_text`, output via the `AgentResponse` JSON schema) - omitted from the base text above since they're not specific to Growth coaching, but present in the actual prompt.
