from typing import Dict, Any

__all__ = [
    "PENDING_LISTINGS",
    "PENDING_SELECTIONS",
    "LAST_VIEWED_PRODUCT",
    "FRESH_BROADCAST_LOCK",
    "SHOWN_PRODUCT_IDS",
    "LAST_REQUESTED_CATEGORY",
    "PENDING_RETURNS",
]

# In-memory store for catalog listings awaiting reseller approval, keyed by
# whatsapp_number + active_mode. A single-process prototype dict is sufficient
# here since there's no multi-worker deployment; a real deployment would
# persist this (e.g. a Supabase table) so approval survives across server
# restarts/workers.
#
# Keying by whatsapp_number alone previously meant Reseller and Customer mode
# shared the same pending-approval slot (both send the same whatsapp_number),
# so a draft awaiting confirmation in Reseller mode would bleed into Customer
# mode's chat. Namespacing the key by mode isolates them.
PENDING_LISTINGS: Dict[str, Dict[str, Any]] = {}

# In-memory store for a ProductGrid picker awaiting a selection, keyed exactly
# like PENDING_LISTINGS/PENDING_RETURNS. Written by run_catalog_agent /
# run_customer_agent when a vector search turns up 2-4 ambiguous SKU matches
# (see ProductGrid.jsx), and resolved by check_pending_selection on the next
# turn - the reseller/customer taps an option, which sends its exact product
# name back as the next message.
PENDING_SELECTIONS: Dict[str, Dict[str, Any]] = {}

# In-memory store for the last specific product a customer was grounded on
# (i.e. the last turn where run_customer_agent's Success Case fired for
# exactly one item), keyed exactly like the dicts above. This app has no real
# cross-turn conversation memory - every /chat/send call is a stateless graph
# invocation - so without this, a natural follow-up confirmation like "isko
# order kar do" or "ye pack kardo" (which doesn't repeat the product name)
# has nothing to resolve against: that message's OWN vector search matches
# loosely against several unrelated catalog items (being a generic phrase
# with no product-specific words), which used to fall through to the
# Browsing Case and show a fresh picker - i.e. an infinite "here are some
# options" loop right when the customer was trying to confirm a purchase.
# This dict is the minimal fix: remember the one item most recently grounded,
# so Priority 2 has a real referent for "isko"/"ye"/"yehi" even when this
# turn's own search can't provide one.
LAST_VIEWED_PRODUCT: Dict[str, Dict[str, Any]] = {}

# One-shot flag: true for exactly the customer's VERY NEXT message after a
# reseller listing is finalized and broadcast into the Customer segment (see
# finalize_catalog_listing), false/absent every other turn. Backs the
# "Latest Context Lock": check_fresh_context_lock pops this (so it can never
# fire twice for the same broadcast) and, if this one message shows buying/
# detail interest, deterministically answers using the just-broadcast product
# instead of letting detect_intent's classifier or a fresh vector search
# route it into the ambiguous-match picker - the "reseller posts an item,
# customer immediately says 'I want to buy' and gets shown unrelated
# alternatives instead" bug. Keyed exactly like LAST_VIEWED_PRODUCT (in fact
# always set alongside it), so it only ever applies to the Customer segment.
FRESH_BROADCAST_LOCK: Dict[str, bool] = {}

# Product IDs already shown to this session in the CURRENT category-scoped
# browse (see run_customer_agent / run_catalog_agent's category-strict
# pagination) - what "show more" excludes so a repeat request never repeats
# an item. Keyed like the dicts above; cleared whenever the session's active
# category actually changes (see LAST_REQUESTED_CATEGORY).
SHOWN_PRODUCT_IDS: Dict[str, list] = {}

# The category this session is currently browsing, if any - lets a bare
# follow-up like "aur dikhao" ("show more") stay scoped to the same category
# without the customer having to repeat it every turn.
LAST_REQUESTED_CATEGORY: Dict[str, str] = {}

# In-memory store for a return in progress awaiting the customer's next reply,
# keyed exactly like PENDING_LISTINGS (whatsapp_number + active_mode) so it
# never bleeds into the Reseller segment. Seeded by run_returns_proactive_outreach
# when the backend system webhook fires (see /api/v1/system/trigger-return) -
# this is the ONLY way a return ever starts. From there, the customer's
# free-text replies are intercepted here turn-by-turn (the graph has no
# persistent thread memory, so without this dict there would be no way to
# know "this customer is mid-return" by the time their next message arrives).
PENDING_RETURNS: Dict[str, Dict[str, Any]] = {}
