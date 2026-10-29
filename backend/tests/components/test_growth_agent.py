"""run_growth_agent: sales coaching from numbers Python computed."""
import pytest

from backend.core.agents import growth
from backend.core.agents.growth import run_growth_agent
from backend.core.gemini_utils import AgentResponse

SALES = [
    {"date": "2026-03-07", "revenue": 1800, "profit": 150, "quantity": 1, "productName": "Saree B", "category": "sarees"},
    {"date": "2026-03-07", "revenue": 900, "profit": 400, "quantity": 3, "productName": "Kurti A", "category": "kurtis"},
    {"date": "2026-02-01", "revenue": 5000, "profit": 2000, "quantity": 9, "productName": "Old Suit", "category": "suits"},
]


@pytest.fixture(autouse=True)
def known_sales(monkeypatch):
    monkeypatch.setattr(growth, "MOCK_SALES_DATA", SALES)


def test_the_model_is_given_the_computed_figures_for_the_window_she_asked_about(sakhi):
    sakhi.gemini.will_return(AgentResponse, ui_text="Report", tts_text="रिपोर्ट")

    run_growth_agent(sakhi.state("pichle 7 din ki sales", mode="reseller"))

    prompt = sakhi.gemini.last_prompt(AgentResponse)
    assert "Timeframe: last 7 days" in prompt
    assert "Total Revenue: 2,700 rupaye" in prompt        # the February suit is outside the window
    assert "Top Category (by revenue): sarees" in prompt
    assert "Most Profitable Category (by profit): kurtis" in prompt


def test_with_gemini_down_the_report_states_the_figures_and_the_real_profit_leader(sakhi):
    state = run_growth_agent(sakhi.state("sales batao", mode="reseller"))

    assert "Total Revenue ₹2,700" in state["reply_text"]
    assert "Total Profit ₹550" in state["reply_text"]
    assert "sabse zyada profit kurtis category se hua" in state["reply_text"]   # used to name sarees


def test_with_no_sales_in_the_window_it_encourages_rather_than_inventing_numbers(sakhi, monkeypatch):
    monkeypatch.setattr(growth, "MOCK_SALES_DATA", [])

    state = run_growth_agent(sakhi.state("sales batao", mode="reseller"))

    assert "koi sales record nahi hui" in state["reply_text"]
    assert "No sales were recorded" in sakhi.gemini.last_prompt(AgentResponse)
