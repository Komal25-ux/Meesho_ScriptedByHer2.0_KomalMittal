# Sakhi — Mentor Call Walkthrough Script

30-minute mentor call. Goal: show understanding and ownership, not just recite the deck.

**Live links:**
- App: https://meesho-sakhi-komal25.vercel.app/
- Backend: https://sakhi-backend-cbmz.onrender.com

⚠️ Backend is on Render free tier — hit the backend URL a minute before the call to warm it up before demoing.

**Jargon to avoid saying out loud:** "RAG." Describe what it does, not the acronym (see Section 4 for exact phrasing). If pushed, there's a one-level-deeper answer ready that still doesn't name it.

---

## Timing

| Time | Section |
|---|---|
| 0–3 min | Hook: Sunita, the problem |
| 3–6 min | Solution overview: what Sakhi is |
| 6–8 min | Live demo |
| 8–16 min | Architecture deep dive |
| 16–20 min | The 5 real engineering problems solved |
| 20–24 min | Impact / business case |
| 24–27 min | Roadmap — what's real vs. mocked |
| 27–30 min | Q&A buffer |

---

## 1. The hook (0–3 min)

Open with the person, not the tech.

> "I want to start with one person: Sunita. She's a Meesho reseller since 2022, sells sarees to 200+ WhatsApp customers, and earns ₹6,200 a month. But she's not running a business — she's running four-hour shifts she can't escape: forwarding the same screenshots to 8 WhatsApp groups by hand, answering 'size kya hai didi?' 40 times a day, calculating margins on a calculator sale-by-sale, and losing sales to returns she has no time to save. She's one of 1.7 crore Meesho resellers, and ~80% of them are women in this exact position."

Turn: *"What if she had a business partner who never sleeps?"* — that's Sakhi.

---

## 2. What Sakhi is (3–6 min)

> "Sakhi isn't a chatbot. It's an agentic AI co-pilot — four specialist agents coordinated by one orchestrator — that Sunita talks to like a friend, on WhatsApp, in Hindi, by voice. No app to download, no English to learn."

The four agents, framed by what they do for her:
- **Catalog Agent** — turns a product link into a ready-to-share Hindi post with her exact margin, in ~20 seconds.
- **Customer Agent** — answers buyers 24x7, grounded in her real catalog, never guessing.
- **Growth Agent** — a weekly voice note coaching her on what's trending ("Karwa Chauth is coming, stock up on red sarees").
- **Returns Agent** — turns a return into an exchange conversation instead of a lost sale.

---

## 3. Live demo (6–8 min)

Don't skip this — it's the strongest asset, a genuinely deployed app, not a localhost recording.

Show two specific things:
1. **Reseller ↔ Customer toggle** — simulates both sides of a real WhatsApp conversation in one session.
2. **"Orchestrator's Brain" panel** — the live agent trace streaming in real time, so the mentor watches routing happen instead of taking your word for it.

Suggested flow:
1. As reseller: send a product link → watch Catalog Agent draft the Hindi post with margin.
2. Switch to customer view → ask "size kya hai" → watch Customer Agent answer from the real catalog, not a guess.

---

## 4. Architecture deep dive (8–16 min)

Walk the actual request path:

> "A voice note comes in → speech-to-text converts it → the Orchestrator reads intent and routes it → the right specialist agent acts, checking her real catalog data when it needs facts, never inventing them → the reply is composed → text-to-speech converts it back to voice → she hears it on WhatsApp. Round trip, about 5 seconds."

Key points to state with ownership:

- **It's a state machine, not "call the model four times."** One shared state object flows through steps: load memory → check for a pending approval → check for a pending selection → check for a pending return → detect intent → route to the right agent → assemble the final reply. That's what makes it agentic rather than a single prompt — it has state, memory, and human-in-the-loop approval steps (e.g. the reseller confirming a price before a listing goes live).

- **Product answers are grounded, not guessed.** Before the Customer Agent answers a buyer, it searches her actual catalog for the matching product first — it never answers from memory or invents a detail. *(This is the RAG mechanism — described without the acronym. If asked how the matching works: "each product and each question gets converted into a numeric representation of its meaning, so the system finds the closest matching product by similarity, not just exact keyword matching — that's the 'Vector DB' box on the architecture diagram.")*

- **Model resilience.** Real API key rotation and a model fallback chain — if one key hits quota or a model errors, it rotates and retries automatically. Built after hitting real free-tier limits during development, not a hypothetical.

- **Deterministic where it matters.** UI button taps route via a fast pattern-match, not by re-interpreting through the model — so a tap always does the same thing. Free-form voice/text still goes through full model-based routing.

---

## 5. The 5 real engineering problems solved (16–20 min)

Your strongest credibility section — proves you shipped and debugged, not just designed. Walk each as bug → root cause → fix:

1. **Zero-hallucination numbers** — the model was inventing profit figures → moved all math to code, the model only phrases the result in Hindi.
2. **Numbers mispronounced in voice output** (₹54,090 read as "5-4-0-9-0") — root cause was the backend stripping commas → fixed by preserving commas + a Hindi transliteration map.
3. **Deterministic routing** — the model was re-interpreting unambiguous UI taps → fast pattern-match for UI actions, full model routing as fallback for free text.
4. **Context-aware, multi-turn conversations** — the orchestrator now maintains state across turns instead of treating each message in isolation.
5. **Latency** — parallel execution + prompt optimization to get sub-second replies for simple queries.

> "None of these were things I designed for upfront — they're things I found by actually using the product and fixing it."

---

## 5b. Extended engineering challenge log (backup depth, if asked to go further)

Section 5 above is the condensed, deck-friendly version of these five. This is the full list of real problems hit while building — keep this in your back pocket for follow-up questions; don't recite it top to bottom on stage.

| Challenge | Root cause | Solution |
|---|---|---|
| Growth Agent voice output getting cut off mid-sentence | The voice API silently truncates long inputs | Constrained the model itself to a strict "one-breath" output — max 3 short sentences, under 40 words — via prompt rules, plus a safety-net cap that trims at a word boundary (never mid-word) if it ever runs long anyway |
| TTS mispronouncing items/currency | Numbers and product names read digit-by-digit or in broken English | Voice-bound text spells every number fully in words (e.g. "चौवन हज़ार नब्बे रुपये" instead of "54,090"), no Latin digits/English letters allowed in what gets spoken; on-screen text keeps normal comma formatting separately |
| Voice quality degradation / context drift over a conversation | Each turn was losing track of what was said before | Reseller memory and session state reload from the database on every turn, and the system explicitly carries forward "the item just discussed" so later turns stay grounded instead of drifting |
| Customer Agent misreading intent | Free-form intent parsing was inconsistent | Replaced with structured, typed classifiers for each decision point (approval, return reason, exchange confirmation, category) instead of asking the model to freehand-interpret every time |
| Complex Hinglish phrasing | Code-mixed Hindi-English didn't generalize well from a generic prompt | Explicit rules and worked examples for code-mixed phrasing patterns written directly into the prompts, instead of relying on the model to infer them |
| Pronoun resolution ("isko," "ye," "yehi") | A bare pronoun with no product name has nothing to match against | System tracks "the most recently discussed item" as a fallback referent — a pronoun resolves to that specific item, but only if the message doesn't itself name a different product or category |
| Reseller and Customer sessions colliding on the same phone number | Both views shared one state, so a pending action in one leaked into the other | Every pending state (approval, product selection, return) is keyed by phone number *and* active mode together, so reseller-side and customer-side sessions never cross-contaminate |
| AI-generated product images hallucinating details | Letting a model generate/pick imagery risks it inventing a product that doesn't exist | Removed AI image generation entirely — no output schema anywhere even has a field for the model to specify an image. Every image shown is a real catalog photo, selected by fixed Python logic, never the model |
| Price tags on product images | Baking price into an AI-composited image is another hallucination surface | Price is stitched onto the real static photo as a separate UI layer (a price-tag overlay component), computed in code — never rendered into the image itself |
| Building a professional, mobile-first dashboard layout | Needed something usable by a non-technical reseller, not a developer tool | Split-screen chat + live dashboard UI, built with a consistent custom design system rather than default component styling |
| Human-in-the-loop approval | A fully autonomous agent could post a wrong price or mishandle a return with no recourse | Catalog listings and return outcomes pause in a pending state until the reseller explicitly confirms — nothing goes live unattended |

**Product/UX decisions made along the way, and why:**
- **No AI-generated images, full stop** — once one hallucination risk was found in imagery, the simplest fix was removing that entire surface rather than trying to constrain it.
- **Price stamped onto real photos, not generated** — keeps the zero-hallucination guarantee consistent across text *and* images.
- **A notification bell for alerts** — order confirmations and return handoffs needed to surface to the reseller without her having to go hunting for them in a busy chat thread.
- **Return alerts prioritized in that surface** — a return is the moment a sale is at risk of being lost, so it's treated as higher-urgency than a routine update.
- **Clickable product grids instead of a wall of text** — when multiple products match a query, showing a tappable picker is better UX than the model trying to describe 3-4 similar sarees in a paragraph and hoping the buyer picks up the right one.
- **The demo catalog was deliberately seeded with clusters of similar products** — not just 100 random SKUs, but intentional overlap (several similar sarees, etc.) so the disambiguation/picker logic actually gets exercised during a demo, not just the easy single-match path.

---

## 5c. Deep dive: the image whitelist design (be ready to explain this properly)

This is a good one to actually understand end-to-end — it's a clean, specific technical decision with a real "why," which is exactly what an interviewer probes on.

**The problem:** letting a model decide what image to show a customer is a hallucination risk — it could invent a product photo, misattribute one, or (if asked to just output a URL) mangle it, since reproducing a ~70-character CDN URL byte-for-byte in JSON is itself an accuracy risk, separate from hallucination.

**The core design decision — whitelist, not blacklist:** there are two ways to gate something risky like this —
- *Blacklist (default-allow):* let it happen by default, and enumerate every case where it *shouldn't*. Fragile — you have to think of every excluded case in advance, and miss one, you leak a bug.
- *Whitelist (default-deny):* block it by default, and enumerate only the few cases where it's explicitly *allowed*. The default is safe even if you missed a case.

Sakhi uses a whitelist, at two layers stacked on top of each other:

**Layer 1 — structural (applies everywhere, no exceptions):** no output schema the model returns, anywhere in the codebase, even *has* a field for an image URL. It's not "the model is told not to guess an image" — it's structurally incapable of specifying one, because the schema itself doesn't expose that slot. Every `reply_image_url` that ever reaches the frontend is set directly in Python, pulled from the real catalog record, never parsed out of the model's output.

**Layer 2 — behavioral (per-agent, narrow and explicit):** for the three agents that *can* attach an image, each gets its own boolean flag from the model — but the flag defaults false, and only a tightly-scoped case flips it true:

| Agent | Whitelisted condition (image shows) | Everything else (no image) |
|---|---|---|
| Catalog Agent | A real product was actually matched in the catalog for the listing being drafted | No match found → apology/fallback text only |
| Customer Agent | `answered_from_product_context` is true — the agent genuinely answered the buyer's question grounded in a looked-up product | Zero-hallucination fallback, purchase-confirmation handoff, return-retention handoff, greetings, small talk — all explicitly excluded, not just "unhandled" |
| Returns Agent | A specific real alternative product was found *and* is being actively named/recommended to the customer | The plain "we'll offer an exchange" reply with no specific item named, the first ask before an alternative is found, and the final closing confirmation — all null |

Even the *URL itself* in the true case still comes from the real catalog record in Python (`grounding_product.get("base_image_url")` / `pending["proposed_alternative"].get("base_image_url")`), never from the model — so the model's only power is a yes/no signal, not the content. Worst case if the model gets the boolean wrong: a real product photo shows when it shouldn't, or no photo shows when one could have — never a fabricated one.

**One more piece in the same spirit — no AI image generation at all, and no AI image compositing either:** the price tag on a product photo isn't baked into the image by a generation/compositing step (another surface where an image model could distort a real product photo or render numbers wrong) — it's stitched on as a separate UI layer, computed in code, over the untouched real photo.

**If asked "what if the model just lies and sets the flag true anyway when it shouldn't"** — the honest answer: the flag is the one place trust is placed in the model, and that's a deliberate tradeoff — narrowing the "what can go wrong" surface from "any image, any URL, any product" down to "the image of a real, correctly-attributed product might show slightly too eagerly." That's a much smaller failure mode than what the naive "let the model return whatever image_url it wants" design would have allowed.

---

## 6. Impact (20–24 min)

- **For her:** ₹6,200 → ₹11,000+/month projected, 4 hours/day given back, no English/literacy barrier.
- **For Meesho:** retention is Meesho's #1 GMV lever; projected 5–8% relative drop in returns; unlocks Tier 3/4 where no assistant-economy exists today.
- **For Bharat:** at 10% adoption (~17 lakh resellers), ₹8,000+ Cr/year in additional income to women-led households.
- Closing note: **the Bharat Shelf** — Sakhi promoting Self-Help-Group-made products at zero commission, turning each reseller's store into a doorway for other women's livelihoods. Good line to end this section on — shows platform thinking beyond the core feature.

---

## 7. Roadmap — what's real vs. mocked (24–27 min)

Be upfront. Mentors respect honesty about scope more than they penalize it.

**Real today:** all 4 agents live, the orchestrator live, real model/voice/database calls, publicly deployed frontend and backend, ₹0 infra cost via free-tier fallbacks.

**Mocked / next:**
- ~100-SKU catalog stands in for Meesho's real private catalog API.
- WhatsApp is simulated in-app rather than wired to a real messaging Business API yet — though the orchestrator itself doesn't need to change to swap that in.
- Infra will need to move off free-tier ceilings as usage grows.

---

## Anticipated tough questions

- **"Why a graph/state machine instead of just a prompt with tools?"** → State + memory + human-in-the-loop approval (reseller confirming price) genuinely need conditional flow, not one stateless call.
- **"What happens if the model API is down or rate-limited?"** → Real key rotation + model fallback chain — this isn't theoretical, it's why the demo doesn't break on a free-tier key.
- **"How do you know it won't invent a price to a customer?"** → Numbers are code-computed, never model-generated; product facts come from checking the real catalog first, not the model's memory.
- **"Isn't this just a chatbot with extra steps?"** → The distinction is specialization + orchestration + persistent per-reseller memory across sessions, not one system prompt trying to do everything.
- **"How does the product-matching actually work?"** → Use the non-jargon phrasing from Section 4. Only go further ("similarity search over numeric representations") if pushed a second time.
- **"What's the cost model at scale?"** → Be honest: free-tier today; the path is metered API costs per reseller vs. the GMV/retention upside for Meesho. Fine to say "that's the next thing I'd model out."

---

## Reminders

- Don't recite slide text verbatim — a mentor notices rehearsed phrasing vs. real understanding.
- Warm up the Render backend before the call.
- If the deck slide shows "(RAG over her catalog)" in a parenthetical, don't read it aloud — paraphrase using Section 4's wording.
