"""Growth numbers (backend/core/metrics/sales.py). They are computed in Python
and handed to the model as facts, so they have to be exactly right."""
import datetime

import pytest
from hypothesis import given, strategies as st

from backend.core.metrics.sales import _aggregate_sales_for_window, _extract_timeframe_days


# ── how many days she asked about ────────────────────────────────────

@pytest.mark.parametrize("message, days", [
    ("15 din ka data dikhao", 15),
    ("pichle 30 days ka report", 30),
    ("last 10 dino ka profit", 10),
    ("1 day", 1),
    ("30days", 30),                 # no space
    ("PICHLE 20 DIN", 20),
    ("999 din", 999),               # largest count read
])
def test_a_day_count_is_read_from_the_message(message, days):
    assert _extract_timeframe_days(message) == days


@pytest.mark.parametrize("message", [
    "aaj ka data",                  # no number
    "0 din ka data",                # zero days means nothing
    "1000 din",                     # four digits is not read as a day count
    "15 saree bik gayi",            # a number, but not of days
])
def test_anything_else_uses_the_default_window(message):
    assert _extract_timeframe_days(message, default_days=14) == 14


def test_the_default_window_is_a_week():
    assert _extract_timeframe_days("sales kaisi rahi") == 7


@pytest.mark.xfail(strict=True, reason="weeks and months are not parsed yet; 'pichle mahine' falls back to 7 days")
def test_last_month_is_thirty_days():
    assert _extract_timeframe_days("pichle mahine ki sales") == 30


# ── aggregating a window ─────────────────────────────────────────────

def sale(date, revenue, profit, quantity, name, category):
    return {"date": date, "revenue": revenue, "profit": profit, "quantity": quantity,
            "productName": name, "category": category}


# Built so every "top" differs: sarees sell the most (revenue), kurtis earn
# the most (profit), and Kurti A sells the most pieces.
SALES = [
    sale("2026-03-01", 1000, 250, 2, "Kurti A", "kurtis"),
    sale("2026-03-05", 1800, 150, 1, "Saree B", "sarees"),
    sale("2026-03-06", 400, 300, 1, "Suit C", "suits"),
    sale("2026-03-07", 500, 150, 3, "Kurti A", "kurtis"),
]


@pytest.mark.parametrize("days, orders", [
    (1, 1),      # just the latest day
    (3, 3),      # 05, 06, 07: the window includes both ends
    (6, 3),      # 02..07: 01 is one day outside
    (7, 4),      # 01..07
    (365, 4),    # longer than the data
])
def test_the_window_counts_back_from_the_latest_sale(days, orders):
    assert _aggregate_sales_for_window(SALES, days)["order_count"] == orders


def test_totals_cover_only_the_window():
    metrics = _aggregate_sales_for_window(SALES, 3)

    assert metrics["days"] == 3
    assert metrics["total_revenue"] == 1800 + 400 + 500
    assert metrics["total_profit"] == 150 + 300 + 150


def test_the_top_category_by_revenue_and_by_profit_are_reported_separately():
    metrics = _aggregate_sales_for_window(SALES, 7)

    assert metrics["top_selling_item"] == "Kurti A"          # 5 pieces
    assert metrics["top_category"] == "sarees"               # ₹1800 revenue
    assert metrics["most_profitable_category"] == "kurtis"   # ₹400 profit; the coaching used to name sarees


def test_sales_of_the_same_item_and_category_add_up_across_rows():
    # Two small sales must beat one bigger one: 2 + 2 > 3 pieces, 300 + 300 > 500 rupees.
    rows = [
        sale("2026-03-01", 300, 50, 2, "Kurti A", "kurtis"),
        sale("2026-03-02", 500, 90, 3, "Saree B", "sarees"),
        sale("2026-03-03", 300, 50, 2, "Kurti A", "kurtis"),
    ]

    metrics = _aggregate_sales_for_window(rows, 7)

    assert (metrics["top_selling_item"], metrics["top_category"], metrics["most_profitable_category"]) == \
        ("Kurti A", "kurtis", "kurtis")


def test_a_window_of_zero_days_is_empty_rather_than_an_error():
    metrics = _aggregate_sales_for_window(SALES, 0)

    assert metrics["order_count"] == 0
    assert (metrics["top_selling_item"], metrics["top_category"], metrics["most_profitable_category"]) == (None, None, None)


def test_ties_go_to_whichever_came_first_so_the_report_never_flips():
    tied = [sale("2026-03-01", 500, 100, 1, "A", "tops"), sale("2026-03-01", 500, 100, 1, "B", "dresses")]

    metrics = _aggregate_sales_for_window(tied, 7)

    assert (metrics["top_selling_item"], metrics["top_category"], metrics["most_profitable_category"]) == ("A", "tops", "tops")


def test_no_sales_gives_zeros_and_no_names():
    metrics = _aggregate_sales_for_window([], 7)

    assert metrics == {"days": 7, "total_revenue": 0, "total_profit": 0, "top_selling_item": None,
                       "top_category": None, "most_profitable_category": None, "order_count": 0}


sales_lists = st.lists(
    st.builds(
        sale,
        date=st.dates(datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)).map(str),
        revenue=st.integers(0, 5000), profit=st.integers(0, 2000), quantity=st.integers(1, 5),
        name=st.sampled_from(["A", "B", "C"]), category=st.sampled_from(["sarees", "kurtis", "suits"]),
    ),
    min_size=1, max_size=30,
)


@given(sales=sales_lists, days=st.integers(1, 120))
def test_a_longer_window_never_shows_less(sales, days):
    shorter = _aggregate_sales_for_window(sales, days)
    longer = _aggregate_sales_for_window(sales, days + 1)
    assert longer["order_count"] >= shorter["order_count"]
    assert longer["total_revenue"] >= shorter["total_revenue"]


@given(sales=sales_lists)
def test_a_window_covering_all_the_data_adds_up_to_everything(sales):
    metrics = _aggregate_sales_for_window(sales, 365)
    assert metrics["total_revenue"] == sum(s["revenue"] for s in sales)
    assert metrics["order_count"] == len(sales)
