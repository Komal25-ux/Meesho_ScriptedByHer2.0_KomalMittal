import pytest
from unittest.mock import patch, MagicMock

from backend.core.agents.growth import run_growth_agent
from backend.core.gemini_utils import AgentResponse


def test_growth_agent_llm_success(make_state):
    state = make_state(raw_input="sales report dikhao", reseller_name="Sunita Didi")
    mock_resp = AgentResponse(
        ui_text="Namaste Sunita Didi! Aapka pichle 7 din ka revenue ₹5,000 raha. 📊",
        tts_text="नमस्ते सुनीता दीदी! आपका पिछले सात दिन का रेवेन्यू पाँच हज़ार रुपये रहा।"
    )

    with patch("backend.core.agents.growth.generate_structured_with_fallback", return_value=mock_resp) as mock_llm, \
         patch("backend.core.agents.growth.db_client.log_agent_event") as mock_log:

        res_state = run_growth_agent(state)

        assert res_state["reply_text"] == mock_resp.ui_text
        assert res_state["reply_tts_text"] == mock_resp.tts_text
        assert len(res_state["trace_logs"]) == 1
        assert res_state["trace_logs"][0]["agent"] == "GrowthAgent"
        assert res_state["trace_logs"][0]["action"] == "Sales Coaching & Metrics Analysis"

        mock_llm.assert_called_once()
        mock_log.assert_called_once()
        call_payload = mock_log.call_args[0][0]
        assert call_payload["event_type"] == "growth_analytics"
        assert call_payload["agent_name"] == "GrowthAgent"
        assert call_payload["session_id"] == state["whatsapp_number"]


def test_growth_agent_llm_fallback_with_sales(make_state):
    state = make_state(raw_input="pichle 10 din ka report", reseller_name="Suneeta")
    mock_metrics = {
        "days": 10,
        "total_revenue": 12500,
        "total_profit": 3200,
        "top_selling_item": "Cotton Kurti",
        "top_category": "kurtis",
        "order_count": 8,
    }

    with patch("backend.core.agents.growth.generate_structured_with_fallback", return_value=None), \
         patch("backend.core.agents.growth._aggregate_sales_for_window", return_value=mock_metrics), \
         patch("backend.core.agents.growth.db_client.log_agent_event"):

        res_state = run_growth_agent(state)

        assert "Namaste Suneeta didi! Pichle 10 din ka business analysis:" in res_state["reply_text"]
        assert "Total Revenue ₹12,500" in res_state["reply_text"]
        assert "Total Profit ₹3,200" in res_state["reply_text"]
        assert "Cotton Kurti" in res_state["reply_text"]
        assert "kurtis" in res_state["reply_text"]
        assert "Cotton Kurti" in res_state["reply_tts_text"]


def test_growth_agent_llm_fallback_zero_sales(make_state):
    state = make_state(raw_input="pichle 30 din ka report", reseller_name="Radha")
    mock_metrics = {
        "days": 30,
        "total_revenue": 0,
        "total_profit": 0,
        "top_selling_item": None,
        "top_category": None,
        "order_count": 0,
    }

    with patch("backend.core.agents.growth.generate_structured_with_fallback", return_value=None), \
         patch("backend.core.agents.growth._aggregate_sales_for_window", return_value=mock_metrics), \
         patch("backend.core.agents.growth.db_client.log_agent_event"):

        res_state = run_growth_agent(state)

        assert "koi sales record nahi hui" in res_state["reply_text"]
        assert "कोई सेल्स रिकॉर्ड नहीं हुई" in res_state["reply_tts_text"]
        assert "Radha" in res_state["reply_text"]


def test_growth_agent_extracts_requested_timeframe(make_state):
    state = make_state(raw_input="15 din ka profit batao")

    with patch("backend.core.agents.growth.generate_structured_with_fallback") as mock_llm, \
         patch("backend.core.agents.growth.db_client.log_agent_event") as mock_log:

        mock_llm.return_value = AgentResponse(ui_text="ok", tts_text="ok")
        res_state = run_growth_agent(state)

        # Check telemetry payload records 15 days
        assert res_state["trace_logs"][0]["data"]["requested_days"] == 15
        mock_log_call = mock_log.call_args[0][0]
        assert mock_log_call["payload"]["requested_days"] == 15
