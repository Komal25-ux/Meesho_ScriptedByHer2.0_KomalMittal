import pytest
from backend.core.rag.formatting import _format_product_line, _format_alternative_context


def test_format_product_line_full():
    product = {
        "name": "Red Banarasi Silk Saree",
        "suggested_selling_price_inr": 599,
        "category": "sarees",
        "sizes": ["Free Size"],
        "colors": ["Red", "Gold"],
        "material": "Banarasi Silk",
        "return_window_days": 7,
        "description": "Elegant red Banarasi silk saree with gold zari borders."
    }
    line = _format_product_line(product)
    expected = (
        "Product: Red Banarasi Silk Saree | Availability: In Stock | Price: 599 rupaye | "
        "Category: sarees | Sizes: Free Size | Colors: Red, Gold | Material: Banarasi Silk | "
        "Return window: 7 days | Description: Elegant red Banarasi silk saree with gold zari borders."
    )
    assert line == expected


def test_format_product_line_missing_optional_fields():
    product = {
        "name": "Blue Kurti",
        "suggested_selling_price_inr": 399,
        "category": "kurtis",
        "sizes": [],
        "colors": None,
        "material": None,
        "return_window_days": 7,
        "description": "Simple blue kurti."
    }
    line = _format_product_line(product)
    assert "Sizes: Not specified" in line
    assert "Colors: Not specified" in line
    assert "Material: Not specified" in line
    assert "Price: 399 rupaye" in line


def test_format_product_line_empty_product():
    product = {}
    line = _format_product_line(product)
    assert "Product: None" in line
    assert "Price: None rupaye" in line
    assert "Sizes: Not specified" in line
    assert "Colors: Not specified" in line
    assert "Material: Not specified" in line


def test_format_alternative_context_scenario_b():
    pending = {
        "proposed_alternative": {
            "name": "Red Banarasi Silk Saree L",
            "suggested_selling_price_inr": 699,
            "sizes": ["L", "XL"],
            "colors": ["Red"]
        }
    }
    alt_context = _format_alternative_context(pending, "B")
    expected = "ALTERNATIVE_PRODUCT: Red Banarasi Silk Saree L | Price: 699 rupaye | Sizes: L, XL | Colors: Red"
    assert alt_context == expected


def test_format_alternative_context_scenario_c():
    pending = {
        "proposed_alternative": {
            "name": "Green Banarasi Silk Saree",
            "suggested_selling_price_inr": 599,
            "sizes": ["Free Size"],
            "colors": ["Green"]
        }
    }
    alt_context = _format_alternative_context(pending, "C")
    expected = "ALTERNATIVE_PRODUCT: Green Banarasi Silk Saree | Price: 599 rupaye | Sizes: Free Size | Colors: Green"
    assert alt_context == expected


def test_format_alternative_context_scenario_a():
    pending = {
        "proposed_alternative": {
            "name": "Some Alternative"
        }
    }
    # For scenario A, alternative is N/A regardless of proposed_alternative
    alt_context = _format_alternative_context(pending, "A")
    assert alt_context == "ALTERNATIVE_PRODUCT: N/A (not applicable at this stage)."


def test_format_alternative_context_missing_alternative():
    pending = {}
    alt_context = _format_alternative_context(pending, "B")
    assert alt_context == "ALTERNATIVE_PRODUCT: N/A (not applicable at this stage)."
