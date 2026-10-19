import pytest
from unittest.mock import patch
from backend.core.rag.retrieval import _lookup_product_by_name, _find_alternative_product


def test_lookup_product_by_name_success():
    with patch("backend.core.rag.retrieval.db_client.match_products") as mock_match, \
         patch("backend.core.rag.retrieval._embed_text", return_value=[0.1] * 768) as mock_embed:

        mock_match.return_value = [{"product_id": "SKU_001", "name": "Red Saree"}]

        result = _lookup_product_by_name("Red Saree")

        assert result is not None
        assert result["name"] == "Red Saree"
        mock_embed.assert_called_once_with("Red Saree")
        mock_match.assert_called_once_with([0.1] * 768, threshold=0.15, limit=1)


def test_lookup_product_by_name_not_found():
    with patch("backend.core.rag.retrieval.db_client.match_products") as mock_match, \
         patch("backend.core.rag.retrieval._embed_text", return_value=[0.1] * 768):

        mock_match.return_value = []

        result = _lookup_product_by_name("Nonexistent Product")
        assert result is None


def test_find_alternative_product_excludes_original():
    orig_product = {"product_id": "SKU_001", "name": "Red Saree", "category": "sarees"}
    candidate_1 = {"product_id": "SKU_001", "name": "Red Saree"}  # Same product
    candidate_2 = {"product_id": "SKU_002", "name": "Blue Saree"} # Alternative

    with patch("backend.core.rag.retrieval.db_client.match_products") as mock_match, \
         patch("backend.core.rag.retrieval._embed_text", return_value=[0.2] * 768) as mock_embed:

        mock_match.return_value = [candidate_1, candidate_2]

        result = _find_alternative_product(orig_product, "blue color")

        assert result is not None
        assert result["product_id"] == "SKU_002"
        assert result["name"] == "Blue Saree"
        mock_embed.assert_called_once_with("sarees blue color")
        mock_match.assert_called_once_with([0.2] * 768, threshold=0.15, limit=3)


def test_find_alternative_product_none_found():
    orig_product = {"product_id": "SKU_001", "name": "Red Saree", "category": "sarees"}

    with patch("backend.core.rag.retrieval.db_client.match_products") as mock_match, \
         patch("backend.core.rag.retrieval._embed_text", return_value=[0.2] * 768):

        # Only returns original product
        mock_match.return_value = [{"product_id": "SKU_001", "name": "Red Saree"}]

        result = _find_alternative_product(orig_product, "larger size")
        assert result is None
