import pytest
from unittest.mock import patch
from backend.core.rag.embeddings import _embed_text


def test_embed_text_delegation():
    with patch("backend.core.rag.embeddings.embed_content_with_fallback") as mock_embed:
        mock_embed.return_value = [0.1] * 768
        res = _embed_text("sample product search query")

        assert res == [0.1] * 768
        mock_embed.assert_called_once_with(
            "sample product search query",
            task_type="retrieval_query",
            output_dimensionality=768
        )


def test_embed_text_empty_string():
    with patch("backend.core.rag.embeddings.embed_content_with_fallback") as mock_embed:
        mock_embed.return_value = []
        res = _embed_text("")
        assert res == []
        mock_embed.assert_called_once_with("", task_type="retrieval_query", output_dimensionality=768)
