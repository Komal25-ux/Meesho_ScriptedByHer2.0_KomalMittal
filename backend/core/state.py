from typing import TypedDict, Optional, List, Dict, Any

__all__ = ["SakhiState"]


class SakhiState(TypedDict):
    reseller_id: str
    whatsapp_number: str
    raw_input: str
    input_type: str
    active_mode: str  # 'reseller' or 'customer' - toggled from the frontend UI

    # Reseller details
    reseller_name: str
    reseller_location: str
    reseller_language: str
    reseller_dialect: str

    # Intent
    detected_intent: str
    intent_confidence: float

    # Human-in-the-loop catalog approval routing (transient, not persisted)
    pending_route: str
    # Human-in-the-loop Returns Retention routing (transient, not persisted)
    pending_return_route: str
    # ProductGrid picker routing (transient, not persisted)
    pending_selection_route: str
    # Latest Context Lock routing (transient, not persisted)
    context_lock_route: str

    # Processing outputs
    reply_text: str
    reply_audio_b64: Optional[str]
    reply_image_url: Optional[str]
    # Selling price for the product shown in reply_image_url, if any - rendered
    # by the frontend as a PricePatch stitched below the image instead of an
    # AI-composited price overlay baked into the image itself.
    reply_price: Optional[int]
    # Up to 4 {name, price, base_image_url} dicts - Python-controlled, never
    # model-emitted (same image_url fidelity policy as elsewhere in this
    # file), rendered by the frontend as a ProductGrid picker when a vector
    # search turns up multiple ambiguous SKU matches.
    reply_product_options: Optional[List[Dict[str, Any]]]
    # Pure Devanagari version of reply_text for Sarvam TTS (dual-output from
    # the same LLM call as reply_text). Falls back to reply_text at the API
    # layer if a node doesn't set this (e.g. deterministic template replies).
    reply_tts_text: Optional[str]

    # Set when a catalog listing was just finalized this turn, so the API
    # layer can broadcast the post into the Customer segment's chat.
    listing_finalized: bool
    listing_broadcast_caption: Optional[str]
    listing_broadcast_caption_tts: Optional[str]
    # Clean, unparsed product identity for the listing finalized this turn -
    # reply_text only has this baked into markdown prose ("Ho gaya Didi!
    # *{name}* ..."), which is fine for display but not something the
    # frontend should have to scrape back out to know which product/category
    # just went live (e.g. to reflect a brand-new-to-Past-Orders SKU in the
    # Catalog dashboard with its just-set price and 0 sales so far).
    listing_product_name: Optional[str]
    listing_category: Optional[str]

    # Set when this turn confirmed a customer purchase (Priority 2 in
    # run_customer_agent), so the API layer can surface it to the Reseller
    # segment's Notification Bell.
    reply_purchase_intent_detected: bool
    # The persisted orders.id this turn's confirmation was written to - see
    # run_customer_agent's Priority 2 handler. The three fields below are
    # read back from that same saved row, never re-derived from session
    # state afterward, so the reseller notification can never drift from
    # what was actually confirmed and stored at checkout.
    reply_order_id: Optional[str]
    reply_confirmed_product_name: Optional[str]
    reply_confirmed_product_price: Optional[int]
    reply_confirmed_product_is_unlisted: Optional[bool]
    # Set when this turn was a terminal Returns Retention Funnel handoff to
    # the human reseller (Scenario A hard-return or Scenario E exchange-
    # confirmed - see check_pending_return), for the same Notification Bell.
    reply_handoff_triggered: bool

    # Tracking telemetry for dashboard
    trace_logs: List[Dict[str, Any]]

    # DB models context
    context_data: Optional[Dict[str, Any]]
