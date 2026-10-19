import pytest
from unittest.mock import patch
from backend.core.catalog.captions import generate_whatsapp_caption
from backend.core.gemini_utils import CatalogCaptionResponse


def test_generate_whatsapp_caption_llm_success():
    mock_resp = CatalogCaptionResponse(
        ui_text="🌸 *Silk Kurti* 🌸\nPrice: ₹599\nOrder karne ke liye mujhe WhatsApp message karein! 🌸",
        tts_text="सिल्क कुर्ती, प्राइस 599 रुपये",
        product_name_tts="सिल्क कुर्ती"
    )
    with patch("backend.core.catalog.captions.generate_structured_with_fallback", return_value=mock_resp) as mock_llm:
        res = generate_whatsapp_caption("Sunita", "Silk Kurti", "Pure silk", 599)
        assert res is mock_resp
        assert res.ui_text == mock_resp.ui_text
        assert mock_llm.called


def test_generate_whatsapp_caption_llm_fallback():
    # When LLM fails, deterministic fallback is returned
    with patch("backend.core.catalog.captions.generate_structured_with_fallback", return_value=None):
        res = generate_whatsapp_caption("Sunita", "Cotton Saree", "Pure cotton", 499)
        assert res is not None
        assert isinstance(res, CatalogCaptionResponse)
        assert "*Cotton Saree*" in res.ui_text
        assert "Final Price: ₹499" in res.ui_text
        assert res.product_name_tts == "Cotton Saree"
