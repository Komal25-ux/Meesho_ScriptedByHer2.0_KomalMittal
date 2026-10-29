"""Finding a product to offer in an exchange (backend/core/rag/retrieval.py).
Only real catalog products are ever offered."""
from backend.core.rag.retrieval import _find_alternative_product, _lookup_product_by_name

from backend.tests.support.catalog import BLUE_SAREE, GREEN_SUIT, PINK_KURTI, WHITE_KURTI


def test_the_returned_product_is_found_in_the_catalog_by_name(sakhi):
    assert _lookup_product_by_name("Pink Cotton Kurti")["product_id"] == PINK_KURTI["product_id"]


def test_an_unknown_product_name_finds_nothing(sakhi):
    assert _lookup_product_by_name("Mystery Dupatta") is None


def test_the_alternative_is_from_the_same_category_and_never_the_returned_product(sakhi):
    alternative = _find_alternative_product(WHITE_KURTI, "different size")

    assert alternative["category"] == "kurtis"
    assert alternative["product_id"] != WHITE_KURTI["product_id"]


def test_when_the_returned_product_is_the_only_one_of_its_kind_there_is_no_alternative(sakhi):
    assert _find_alternative_product(GREEN_SUIT, "different color") is None


def test_a_database_failure_is_not_mistaken_for_no_alternative(sakhi):
    import pytest
    from backend.errors import DependencyUnavailable
    sakhi.db.fail("match_products")

    with pytest.raises(DependencyUnavailable):
        _find_alternative_product(BLUE_SAREE, "different color")
