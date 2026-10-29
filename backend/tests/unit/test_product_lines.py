"""The product facts an agent is grounded on (backend/core/rag/formatting.py).
Whatever is not in these lines, the model has no business stating."""
from backend.core.rag.formatting import _format_alternative_context, _format_product_line

from backend.tests.support.catalog import PINK_KURTI


def test_a_product_line_carries_every_fact_a_buyer_may_ask_about():
    line = _format_product_line(PINK_KURTI)

    for fact in ["Pink Cotton Kurti", "Price: 399 rupaye", "Category: kurtis", "Sizes: S, M, L, XL",
                 "Colors: Pink", "Material: Cotton", "Return window: 7 days"]:
        assert fact in line


def test_a_missing_fact_is_written_as_not_specified_so_it_is_never_guessed():
    line = _format_product_line({"name": "Plain Top", "sizes": [], "colors": None})

    assert "Sizes: Not specified" in line
    assert "Colors: Not specified" in line
    assert "Material: Not specified" in line


def test_an_alternative_is_offered_only_for_size_and_colour_complaints():
    pending = {"proposed_alternative": PINK_KURTI}

    for stage in ("B", "C"):
        assert "ALTERNATIVE_PRODUCT: Pink Cotton Kurti" in _format_alternative_context(pending, stage)
    for stage in ("A", "D", "E"):
        assert "N/A" in _format_alternative_context(pending, stage)


def test_no_alternative_found_means_none_is_offered():
    assert "N/A" in _format_alternative_context({}, "B")
