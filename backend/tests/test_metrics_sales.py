import pytest
from backend.core.metrics.sales import _extract_timeframe_days, _aggregate_sales_for_window


@pytest.mark.parametrize("user_input, default_days, expected", [
    ("15 din ka data dikhao", 7, 15),
    ("pichle 30 days ka report", 7, 30),
    ("last 10 dino ka profit", 7, 10),
    ("aaj ka data", 7, 7),
    ("kuch bhi", 14, 14),
    ("0 din ka data", 7, 7),
])
def test_extract_timeframe_days(user_input, default_days, expected):
    assert _extract_timeframe_days(user_input, default_days) == expected


def test_aggregate_sales_for_window_empty():
    res = _aggregate_sales_for_window([], 7)
    assert res == {
        "days": 7,
        "total_revenue": 0,
        "total_profit": 0,
        "top_selling_item": None,
        "top_category": None,
        "order_count": 0,
    }


def test_aggregate_sales_for_window_normal():
    transactions = [
        {"date": "2026-03-01", "revenue": 1000, "profit": 250, "quantity": 2, "productName": "Kurti A", "category": "kurtis"},
        {"date": "2026-03-05", "revenue": 1500, "profit": 400, "quantity": 1, "productName": "Saree B", "category": "sarees"},
        {"date": "2026-03-07", "revenue": 500, "profit": 150, "quantity": 3, "productName": "Kurti A", "category": "kurtis"},
    ]
    # Window of 3 days ending at latest date 2026-03-07 (from 2026-03-05 to 2026-03-07)
    res = _aggregate_sales_for_window(transactions, 3)

    assert res["days"] == 3
    assert res["total_revenue"] == 2000 # 1500 + 500
    assert res["total_profit"] == 550   # 400 + 150
    assert res["order_count"] == 2
    assert res["top_selling_item"] == "Kurti A" # quantity 3 vs 1
    assert res["top_category"] == "sarees"      # revenue 1500 vs 500
