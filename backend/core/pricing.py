"""Selling-price rules, and reading a price out of a reseller's message.

Both used to be inlined - the margin rule in four places across the catalog
and customer agents, price parsing twice with two different behaviours - so
they live here once and are tested directly.
"""
import re
from typing import Optional

__all__ = ["MIN_PROFIT_INR", "MIN_MARGIN_PERCENT", "suggested_price", "requested_price", "mentioned_prices"]

MIN_PROFIT_INR = 150
MIN_MARGIN_PERCENT = 30

# A price a reseller would actually type. Anything outside this is a size, a
# quantity, a year or a typo, not a price.
_MIN_PRICE_INR = 10
_MAX_PRICE_INR = 999_999


def suggested_price(cost_inr: int) -> int:
    """Default price for a product the reseller hasn't priced herself: at
    least MIN_PROFIT_INR profit and at least a MIN_MARGIN_PERCENT margin on
    the selling price, whichever is higher.

    Integer arithmetic on purpose. The old int(cost / 0.7) truncated, which
    left the margin just under 30% for most costs (cost 351 -> 501 is
    29.94%), and 350 / 0.7 is 500.00000000000006 in floating point.
    """
    keep_percent = 100 - MIN_MARGIN_PERCENT
    margin_floor = -(-cost_inr * 100 // keep_percent)  # ceil(cost / 0.70)
    return max(cost_inr + MIN_PROFIT_INR, margin_floor)


# "₹599", "Rs. 599", "INR 599", "price 599", "599/-", "599 rupaye", "599 रुपये"
_AMOUNT = r"(\d{1,3}(?:,\d{2,3})+|\d+)"
_MARKED_AMOUNT = re.compile(
    rf"(?:₹|\brs\.?|\binr\b|\b(?:price|rate|kimat|keemat|daam|mrp)\s*(?:is|hai|:|-)?)\s*{_AMOUNT}(?![\d,])"
    rf"|(?<![\d,]){_AMOUNT}\s*(?:/-|\brupa\w*|\brupee\w*|\brs\b|रुपय|रुपए|रूपए|रूपये)",
    re.IGNORECASE,
)


def _amount_of(match: "re.Match[str]") -> str:
    return match.group(1) or match.group(2)
_BARE_AMOUNT = re.compile(rf"(?<![\d,]){_AMOUNT}(?![\d,])")
# A bare number right before or after one of these is not a price.
_NOT_A_PRICE_BEFORE = re.compile(r"\b(?:size|no\.?|number)\s*$", re.IGNORECASE)
_NOT_A_PRICE_AFTER = re.compile(r"^\s*(?:%|percent|din\b|dino\b|day|size\b|cm\b|inch|pcs\b|piece|set\b)", re.IGNORECASE)


def _to_rupees(digits: str) -> Optional[int]:
    value = int(digits.replace(",", ""))
    return value if _MIN_PRICE_INR <= value <= _MAX_PRICE_INR else None


def requested_price(text: str) -> Optional[int]:
    """The price a message asks for, if it names one.

    An amount marked as money (₹, Rs, /-, rupaye...) wins over a bare number,
    so "size 42 wali 599 rupaye me kar do" is 599, not 42. Otherwise the
    first bare number that isn't next to a size/day/percent word is used.
    Thousands separators are understood in both styles ("5,999", "1,00,000");
    without that, "5,999" used to be read as 999.
    """
    for match in _MARKED_AMOUNT.finditer(text):
        price = _to_rupees(_amount_of(match))
        if price is not None:
            return price
    for match in _BARE_AMOUNT.finditer(text):
        if _NOT_A_PRICE_BEFORE.search(text[: match.start()]) or _NOT_A_PRICE_AFTER.match(text[match.end():]):
            continue
        price = _to_rupees(match.group(1))
        if price is not None:
            return price
    return None


def mentioned_prices(text: str) -> list:
    """Every amount `text` states as money ("₹599", "599 rupaye", "599
    रुपये"...), in order. Unlike requested_price there are no bounds and no
    bare numbers: this is for checking what a reply claims, where "size 42"
    must not count but "₹1" must."""
    return [int(_amount_of(m).replace(",", "")) for m in _MARKED_AMOUNT.finditer(text)]
