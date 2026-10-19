import pytest
from unittest.mock import patch

from backend.core.agents.general import run_general_handler
from backend.core.gemini_utils import AgentResponse


def test_general_handler_llm_success(make_state):
    state = make_state(raw_input="namaste didi", reseller_name="Sunita")
    mock_resp = AgentResponse(
        ui_text="Namaste Sunita didi! Kaise madad karu aapki?",
        tts_text="नमस्ते सुनीता दीदी! कैसे मदद करूँ आपकी?"
    )

    with patch("backend.core.agents.general.generate_structured_with_fallback", return_value=mock_resp) as mock_llm, \
         patch("backend.core.agents.general.db_client.log_agent_event") as mock_log:

        res_state = run_general_handler(state)

        assert res_state["reply_text"] == mock_resp.ui_text
        assert res_state["reply_tts_text"] == mock_resp.tts_text
        assert len(res_state["trace_logs"]) == 1
        assert res_state["trace_logs"][0]["agent"] == "GeneralAgent"
        assert res_state["trace_logs"][0]["action"] == "Conversation greeting handler"

        mock_llm.assert_called_once()
        mock_log.assert_called_once()
        call_payload = mock_log.call_args[0][0]
        assert call_payload["event_type"] == "general_greeting"
        assert call_payload["agent_name"] == "GeneralAgent"
        assert call_payload["session_id"] == state["whatsapp_number"]


def test_general_handler_llm_fallback(make_state):
    state = make_state(raw_input="hello", reseller_name="Komal")

    with patch("backend.core.agents.general.generate_structured_with_fallback", return_value=None), \
         patch("backend.core.agents.general.db_client.log_agent_event"):

        res_state = run_general_handler(state)

        assert "Namaste Komal didi! Main aapki business Sakhi hu." in res_state["reply_text"]
        assert "Main catalog items list kar sakti hu" in res_state["reply_text"]
        assert "नमस्ते Komal दीदी! मैं आपकी बिज़नेस सखी हूँ।" in res_state["reply_tts_text"]
