import re
import datetime
from typing import Dict, Any, List

__all__ = ["_extract_timeframe_days", "_aggregate_sales_for_window"]


def _extract_timeframe_days(user_input: str, default_days: int = 7) -> int:
    """Pulls a requested day-count out of phrasing like "15 din ka data" or
    "pichle 30 days" -> 15 / 30. Deterministic regex, not an LLM call - the
    same reasoning as _extract_price above: pulling one number out of text is
    a task regex handles reliably and near-instantly, so spending a full
    model round-trip on it would only add latency for no accuracy benefit."""
    match = re.search(r"\b(\d{1,3})\s*(?:din|dino|days?)\b", user_input, re.IGNORECASE)
    if match:
        days = int(match.group(1))
        return days if days > 0 else default_days
    return default_days


def _aggregate_sales_for_window(transactions: list, days: int) -> Dict[str, Any]:
    """Filters MOCK_SALES_DATA to the last `days` calendar days ending at the
    dataset's own latest date (derived, not hardcoded, so this stays correct
    if the dataset's range ever changes) and computes the Growth Agent's
    pre-calculated metrics in Python - total_revenue, total_profit, the
    top-selling item by quantity, and the top category by revenue. The LLM
    never sees raw transactions or does this arithmetic itself; it only ever
    receives the already-correct numbers below (same zero-hallucination
    principle as every other RAG-grounded node in this file)."""
    if not transactions:
        return {
            "days": days, "total_revenue": 0, "total_profit": 0,
            "top_selling_item": None, "top_category": None, "order_count": 0
        }

    anchor = max(t["date"] for t in transactions)
    anchor_date = datetime.date.fromisoformat(anchor)
    window_start = anchor_date - datetime.timedelta(days=days - 1)
    window_start_str = window_start.isoformat()

    filtered = [t for t in transactions if window_start_str <= t["date"] <= anchor]

    total_revenue = sum(t["revenue"] for t in filtered)
    total_profit = sum(t["profit"] for t in filtered)

    quantity_by_item: Dict[str, int] = {}
    revenue_by_category: Dict[str, int] = {}
    for t in filtered:
        quantity_by_item[t["productName"]] = quantity_by_item.get(t["productName"], 0) + t["quantity"]
        revenue_by_category[t["category"]] = revenue_by_category.get(t["category"], 0) + t["revenue"]

    top_selling_item = max(quantity_by_item, key=quantity_by_item.get) if quantity_by_item else None
    top_category = max(revenue_by_category, key=revenue_by_category.get) if revenue_by_category else None

    return {
        "days": days,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "top_selling_item": top_selling_item,
        "top_category": top_category,
        "order_count": len(filtered),
    }
