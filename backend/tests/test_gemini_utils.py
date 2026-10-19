import pytest
from unittest.mock import MagicMock, patch
from google.genai import types

from backend.core import gemini_utils


def test_public_schemas_and_functions_present():
    assert hasattr(gemini_utils, "AgentResponse")
    assert hasattr(gemini_utils, "CatalogCaptionResponse")
    assert hasattr(gemini_utils, "CustomerAgentResponse")
    assert hasattr(gemini_utils, "ReturnsAgentResponse")
    assert hasattr(gemini_utils, "IntentRouter")
    assert hasattr(gemini_utils, "configure_gemini")
    assert hasattr(gemini_utils, "rotate_gemini_key")
    assert hasattr(gemini_utils, "generate_with_fallback")
    assert hasattr(gemini_utils, "generate_structured_with_fallback")
    assert hasattr(gemini_utils, "embed_content_with_fallback")


def test_key_rotation_cycle():
    with patch.object(gemini_utils.settings, "GEMINI_API_KEY", "KEY_0"), \
         patch.object(gemini_utils.settings, "GEMINI_API_KEY_FALLBACK", "KEY_1"), \
         patch.object(gemini_utils.settings, "GEMINI_API_KEY_FALLBACK_2", "KEY_2"):

        gemini_utils._CURRENT_KEY_INDEX = 0
        assert gemini_utils._CURRENT_KEY_INDEX == 0
        client0 = gemini_utils._get_active_client()
        assert client0._api_client.api_key == "KEY_0"

        gemini_utils.rotate_gemini_key()
        assert gemini_utils._CURRENT_KEY_INDEX == 1
        client1 = gemini_utils._get_active_client()
        assert client1._api_client.api_key == "KEY_1"

        gemini_utils.rotate_gemini_key()
        assert gemini_utils._CURRENT_KEY_INDEX == 2
        client2 = gemini_utils._get_active_client()
        assert client2._api_client.api_key == "KEY_2"

        gemini_utils.rotate_gemini_key()
        assert gemini_utils._CURRENT_KEY_INDEX == 0
        client3 = gemini_utils._get_active_client()
        assert client3._api_client.api_key == "KEY_0"


def test_model_chain_order():
    with patch.object(gemini_utils.settings, "GEMINI_MODEL", "primary-model"), \
         patch.object(gemini_utils.settings, "GEMINI_FALLBACK_MODELS", "fb-1, fb-2"):
        chain = gemini_utils._model_chain()
        assert chain == ["primary-model", "fb-1", "fb-2"]


def test_generate_with_fallback_model_fallback():
    mock_client = MagicMock()
    call_sequence = []

    def mock_generate(*args, **kwargs):
        model = kwargs.get("model")
        call_sequence.append(model)
        if model == "gemini-flash-lite-latest":
            raise Exception("Quota exceeded 429")
        resp = MagicMock()
        resp.text = "Success output"
        return resp

    mock_client.models.generate_content.side_effect = mock_generate

    with patch("backend.core.gemini_utils._get_active_client", return_value=mock_client), \
         patch("backend.core.gemini_utils._get_gemini_keys", return_value=["KEY_A"]):
        res = gemini_utils.generate_with_fallback("Test prompt")
        assert res == "Success output"
        assert len(call_sequence) == 2
        assert call_sequence[0] == "gemini-flash-lite-latest"
        assert call_sequence[1] == "gemini-3.5-flash-lite"


def test_generate_with_fallback_key_rotation_on_403():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("Invalid API key 403")

    with patch("backend.core.gemini_utils._get_active_client", return_value=mock_client), \
         patch("backend.core.gemini_utils._get_gemini_keys", return_value=["KEY_A", "KEY_B"]), \
         patch("backend.core.gemini_utils.rotate_gemini_key") as mock_rotate:
        res = gemini_utils.generate_with_fallback("Test prompt")
        assert res is None
        # Should attempt key rotation
        assert mock_rotate.called


def test_generate_structured_with_fallback_success():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"ui_text": "Namaste", "tts_text": "नमस्ते"}'
    mock_client.models.generate_content.return_value = mock_resp

    with patch("backend.core.gemini_utils._get_active_client", return_value=mock_client), \
         patch("backend.core.gemini_utils._get_gemini_keys", return_value=["KEY_A"]):
        parsed = gemini_utils.generate_structured_with_fallback("prompt", gemini_utils.AgentResponse)
        assert isinstance(parsed, gemini_utils.AgentResponse)
        assert parsed.ui_text == "Namaste"
        assert parsed.tts_text == "नमस्ते"

        # Verify configuration
        cfg = mock_client.models.generate_content.call_args.kwargs["config"]
        assert cfg.response_mime_type == "application/json"
        assert cfg.response_schema == gemini_utils.AgentResponse


def test_generate_structured_with_fallback_validation_error():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"invalid_field": 123}'  # Missing required fields
    mock_client.models.generate_content.return_value = mock_resp

    with patch("backend.core.gemini_utils._get_active_client", return_value=mock_client), \
         patch("backend.core.gemini_utils._get_gemini_keys", return_value=["KEY_A"]):
        # Model fallback continues when validation fails, eventually returns None
        parsed = gemini_utils.generate_structured_with_fallback("prompt", gemini_utils.AgentResponse)
        assert parsed is None


def test_embed_content_with_fallback():
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = types.EmbedContentResponse(
        embeddings=[types.ContentEmbedding(values=[0.25] * 768)]
    )

    with patch("backend.core.gemini_utils._get_active_client", return_value=mock_client), \
         patch("backend.core.gemini_utils._get_gemini_keys", return_value=["KEY_A"]):
        vec = gemini_utils.embed_content_with_fallback("test text", task_type="retrieval_query", output_dimensionality=768)
        assert len(vec) == 768
        assert vec[0] == 0.25

        kwargs = mock_client.models.embed_content.call_args.kwargs
        assert kwargs["model"] == "models/gemini-embedding-001"
        assert kwargs["contents"] == "test text"
        assert kwargs["config"].task_type == "retrieval_query"
        assert kwargs["config"].output_dimensionality == 768
