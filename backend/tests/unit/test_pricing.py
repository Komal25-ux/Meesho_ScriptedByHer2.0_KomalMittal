"""Pricing rules (backend/core/pricing.py).

suggested_price has two rules that cross over at cost 350, where
cost + 150 == cost / 0.7 == 500. Below it the ₹150 profit floor decides,
above it the 30% margin does, so the boundary cases sit on either side of 350.
"""
import pytest
from hypothesis import given, strategies as st

from backend.core.pricing import MIN_MARGIN_PERCENT, MIN_PROFIT_INR, requested_price, suggested_price


# ── suggested_price ──────────────────────────────────────────────────

@pytest.mark.parametrize("cost, expected", [
    (1, 151),      # tiny cost: profit floor
    (349, 499),    # last cost where the profit floor wins
    (350, 500),    # crossover: both rules give 500 (350 / 0.7 is 500.00000000000006 as a float)
    (351, 502),    # first cost where the margin rule wins; int() truncation gave 501 (29.94%)
    (420, 600),    # exact: 420 / 0.7 == 600
    (700, 1000),
    (701, 1002),   # 1001.43 rounds up, never down
])
def test_suggested_price_at_and_around_the_crossover(cost, expected):
    assert suggested_price(cost) == expected


@given(cost=st.integers(min_value=1, max_value=500_000))
def test_suggested_price_always_keeps_the_minimum_profit(cost):
    assert suggested_price(cost) - cost >= MIN_PROFIT_INR


@given(cost=st.integers(min_value=1, max_value=500_000))
def test_suggested_price_always_keeps_the_minimum_margin(cost):
    price = suggested_price(cost)
    # margin = (price - cost) / price >= 30%, kept in integers
    assert (price - cost) * 100 >= MIN_MARGIN_PERCENT * price


@given(cost=st.integers(min_value=1, max_value=500_000))
def test_suggested_price_is_the_lowest_price_that_satisfies_both_rules(cost):
    cheaper = suggested_price(cost) - 1
    keeps_profit = cheaper - cost >= MIN_PROFIT_INR
    keeps_margin = (cheaper - cost) * 100 >= MIN_MARGIN_PERCENT * cheaper
    assert not (keeps_profit and keeps_margin)


# ── requested_price ──────────────────────────────────────────────────

@pytest.mark.parametrize("message, price", [
    ("599 me list kar do", 599),
    ("price 799 kar do", 799),
    ("₹650", 650),
    ("₹ 650 rakho", 650),
    ("Rs.899 theek hai", 899),
    ("rs 899", 899),
    ("INR 1200", 1200),
    ("599/- me post karo", 599),
    ("450 rupaye", 450),
    ("450 rupees", 450),
    ("5,999 me daal do", 5999),      # used to come back as 999
    ("1,00,000 wali saree", 100000), # Indian grouping
    ("100,000", 100000),
])
def test_requested_price_reads_the_ways_resellers_write_prices(message, price):
    assert requested_price(message) == price


@pytest.mark.parametrize("message, price", [
    ("size 42 wali 599 rupaye me kar do", 599),  # marked amount beats an earlier bare number
    ("42 size, 650 rakho", 650),
    ("size 40", None),
    ("15 din ka data", None),
    ("20% kam karo", None),
    ("set of 3, 899", 899),
    ("15 saree hain, 499 rupaye me lagao", 499),  # a quantity first, then the price
])
def test_requested_price_ignores_numbers_that_are_sizes_days_or_percentages(message, price):
    assert requested_price(message) == price


@pytest.mark.parametrize("message, price", [
    ("9", None),          # below the smallest believable price
    ("10", 10),           # smallest
    ("999999", 999999),   # largest
    ("1000000", None),    # above the largest
    ("₹9", None),
    ("₹1000000", None),
])
def test_requested_price_bounds(message, price):
    assert requested_price(message) == price


@pytest.mark.parametrize("message", ["", "haan post kar do", "kitne ka hai?", "rupaye", "₹"])
def test_requested_price_is_none_when_no_price_is_named(message):
    assert requested_price(message) is None


@given(st.text())
def test_requested_price_is_none_or_a_believable_price_for_any_text(text):
    price = requested_price(text)
    assert price is None or 10 <= price <= 999_999


@given(price=st.integers(min_value=10, max_value=999_999), filler=st.sampled_from(["", "haan ", "theek hai, "]))
def test_requested_price_round_trips_a_rupee_amount(price, filler):
    assert requested_price(f"{filler}₹{price:,}") == price
