# Catalog Agent ('Catalog Didi') Prompt Specification

This file documents the **Catalog Agent** (`run_catalog_agent` in `backend/core/orchestrator.py`), the reseller-facing agent that drafts and posts WhatsApp product listings. Unlike the Growth Agent and Customer Agent, most of Catalog Agent's reply text is **not** LLM-generated - it's deterministic Python string-templating around one focused LLM call (`generate_whatsapp_caption`) that writes only the WhatsApp promotional caption itself. This doc covers both: the Python-level decision flow (source-of-truth for what actually ships) and the one embedded LLM prompt within it.

---

## 1. Why Most of This Agent Is Python, Not a Prompt

Every number a reseller sees here - cost price, suggested selling price, profit margin - comes directly from the seeded catalog (`meesho_cost_inr` / `suggested_selling_price_inr` in `scripts/seed_catalog.py`) or simple arithmetic on it, never from LLM output. Asking a model to also decide/state prices would reproduce the same "reproduction-fidelity risk" this codebase avoids everywhere else (see `prompt_growth_agent.md` §1) for a task Python already does exactly and instantly. `generate_whatsapp_caption` is the one part actually suited to an LLM - writing a warm, persuasive Hinglish promotional post - and even that receives the price as a precomputed input, never inventing it.

## 2. Product Resolution

1. **Exact-name lookup first** (`db_client.get_product_by_name(user_input)`) - this is how a `ProductGrid.jsx` tap (disambiguation picker) or a Product Card Click (§4 below) arrives back here: the frontend always sends back the exact catalog product name, so an exact match resolves instantly without re-running vector search.
2. **Category-strict vector search fallback** - same `extract_category_intent` / `SHOWN_PRODUCT_IDS` pagination pattern used by the Customer Agent, for free-text requests like "yellow saree list karo".
3. **Ambiguous match (2+ candidates, or 1+ within a category)** - shows a `ProductGrid` picker instead of guessing; resolved deterministically by `check_pending_selection` on the next turn.
4. **Single match** - proceeds to draft a listing (§3).

## 3. Draft Listing Flow (Human-in-the-Loop)

Once exactly one product is resolved:
- `cost` = `meesho_cost_inr`; `selling_price` = `suggested_selling_price_inr` (falls back to `cost + 150` if absent), overridden by any digit found in the user's message above `cost`.
- `generate_whatsapp_caption` (the one LLM call - see §5) writes the promotional post.
- The draft is held in `PENDING_LISTINGS` (keyed by whatsapp_number + active_mode) - **nothing is saved or posted yet**. The reseller must explicitly approve, modify the price, or abandon it; `check_pending_approval` classifies which of those the next message is (LLM-classified, not keyword-matched, since "kar do" alone is ambiguous between approval/price-edit/new-request).
- Approval → `finalize_catalog_listing` saves the listing and broadcasts it into the Customer segment's chat. It also seeds that customer session's `LAST_VIEWED_PRODUCT` (see `prompt_customer_agent.md`'s RECENTLY DISCUSSED ITEM section) with the just-posted product - `App.jsx`'s broadcast is purely a cosmetic frontend chat bubble, so without this the Customer Agent has no idea the customer has "seen" the item, and a bare purchase confirmation right after the post (*"ye lena hai"*) would fall through to an ambiguous-match picker instead of confirming the order.

## 4. CRITICAL RULE FOR SHARING (Product Card Click, Reseller Mode)

**Trigger:** the incoming message starts with the exact phrase `"Ye item WhatsApp group mein share karna hai:"` (case-insensitive), followed by a product name. This is sent by exactly one place in the frontend - `handleProductCardClick` in `App.jsx`, on every tap of a product card in Reseller mode (a fresh disambiguation picker, or an old card scrolled back up to). `detect_intent` recognizes this exact prefix and routes straight to `CATALOG` without an LLM classification call (see `CATALOG_SHARE_TRIGGER_RE` in `orchestrator.py`) - a bare product name gave the classifier no verb/intent to key off, which is the ambiguity this trigger phrase exists to eliminate.

**Action:** `run_catalog_agent` strips the trigger prefix (`_strip_trigger_prefix`) back to the bare product name before doing its normal exact-name resolution (§2) and draft flow (§3) - so this reuses the exact same cost/price computation, caption generation, and `PENDING_LISTINGS` approval state machine as any other listing draft. The only thing that changes is the reply text, which must:
1. Acknowledge the selected item by name.
2. Suggest a selling price (`cost` + margin, both Python-sourced from the catalog - never invented).
3. Ask the reseller whether to post it now, or whether they'd like to change the price - in the same message, not as two separate turns.

*Actual reply template (Python, not LLM-generated):*
```text
Zaroor Didi! *{product_name}* ki cost price ₹{cost} hai. Hum isko WhatsApp group mein ₹{selling_price} mein post kar sakte hain (aapka profit ₹{selling_price - cost} hoga).

{whatsapp_caption}

Kya main isko post kar doon, ya aap price change karna chahengi?
```

A "yes" or a new price on the reseller's next message is resolved by the existing `check_pending_approval` / `_extract_price` flow (§3) - no separate state machine was needed for this trigger, since it produces the exact same `PENDING_LISTINGS` entry a normal draft would.

## 5. `generate_whatsapp_caption` Prompt (the one LLM call)

Given `reseller_name`, `product_name`, `product_description`, and `selling_price` (all Python-sourced), writes:
- **ui_text**: the Hinglish WhatsApp caption itself - must include the product name and price, end EXACTLY with `"Order karne ke liye mujhe WhatsApp message karein! 🌸"`, stay under 5 lines, use appropriate emojis.
- **tts_text**: pure Devanagari translation - no Latin letters, no `₹` (spelled out as "रुपये"), no markdown/emoji, "AI Sakhi" always spelled phonetically as "ए आई सखी".
- **product_name_tts**: the product name alone, phonetically transliterated to Devanagari - used whenever a caller echoes the name back inside an otherwise-Devanagari sentence (e.g. the reply templates in §3/§4 above), since Sarvam reads a raw Latin-script name with English stress patterns even mid-Devanagari-sentence otherwise.

## 6. Output Schema (`generate_whatsapp_caption` only)
```json
{
  "ui_text": "string",
  "tts_text": "string",
  "product_name_tts": "string"
}
```
The rest of `run_catalog_agent`'s reply (`reply_text`/`reply_tts_text`) is plain Python string templating, not a structured LLM schema - see §3/§4 above for the actual templates.
