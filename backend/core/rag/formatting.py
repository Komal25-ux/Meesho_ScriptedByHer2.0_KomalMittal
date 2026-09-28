from typing import Dict, Any

__all__ = ["_format_product_line", "_format_alternative_context"]


def _format_product_line(p: Dict[str, Any]) -> str:
    """Renders one product dict as a single grounding line for an LLM prompt -
    shared by run_customer_agent's own CONTEXT/RECENTLY DISCUSSED ITEM blocks
    and check_fresh_context_lock's Latest Context Lock reply, so both ground
    strictly on the same real product fields (never inventing one)."""
    return (
        f"Product: {p.get('name')} | Availability: In Stock | Price: {p.get('suggested_selling_price_inr')} rupaye | "
        f"Category: {p.get('category')} | "
        f"Sizes: {', '.join(p.get('sizes') or []) or 'Not specified'} | "
        f"Colors: {', '.join(p.get('colors') or []) or 'Not specified'} | "
        f"Material: {p.get('material') or 'Not specified'} | "
        f"Return window: {p.get('return_window_days')} days | Description: {p.get('description')}"
    )


def _format_alternative_context(pending: Dict[str, Any], stage_label: str) -> str:
    if stage_label in ("B", "C") and pending.get("proposed_alternative"):
        alt = pending["proposed_alternative"]
        return (
            f"ALTERNATIVE_PRODUCT: {alt.get('name')} | Price: {alt.get('suggested_selling_price_inr')} rupaye | "
            f"Sizes: {', '.join(alt.get('sizes') or []) or 'Not specified'} | "
            f"Colors: {', '.join(alt.get('colors') or []) or 'Not specified'}"
        )
    return "ALTERNATIVE_PRODUCT: N/A (not applicable at this stage)."
