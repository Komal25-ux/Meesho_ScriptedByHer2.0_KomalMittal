"""The fixed phrases the frontend sends when a product card is tapped."""
import pytest

from backend.core.routing.triggers import _strip_trigger_prefix


@pytest.mark.parametrize("sent, product", [
    ("ye item whatsapp group mein share karna hai: Blue Kurti", "Blue Kurti"),
    ("mujhe ye wala item pasand hai, iski details batao: Red Saree", "Red Saree"),
    ("mujhe ye wala item pasand hai iski details batao: Red Saree", "Red Saree"),   # comma is optional
    ("YE ITEM WHATSAPP GROUP MEIN SHARE KARNA HAI: Blue Kurti", "Blue Kurti"),
    ("ye item whatsapp group mein share karna hai:    Blue Kurti  ", "Blue Kurti"),
])
def test_a_card_tap_is_reduced_to_the_product_name(sent, product):
    assert _strip_trigger_prefix(sent) == product


@pytest.mark.parametrize("typed", [
    "kya haal hai",
    "Blue Kurti",
    "please ye item whatsapp group mein share karna hai: Blue Kurti",  # only at the very start
    "",
])
def test_anything_else_is_left_exactly_as_typed(typed):
    assert _strip_trigger_prefix(typed) == typed
