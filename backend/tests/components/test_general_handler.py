from backend.core.agents.general import run_general_handler
from backend.core.gemini_utils import AgentResponse


def test_small_talk_is_answered_by_the_model(sakhi):
    sakhi.gemini.will_return(AgentResponse, ui_text="Namaste didi!", tts_text="नमस्ते दीदी!")

    state = run_general_handler(sakhi.state("namaste", mode="reseller"))

    assert (state["reply_text"], state["reply_tts_text"]) == ("Namaste didi!", "नमस्ते दीदी!")


def test_with_gemini_down_sakhi_introduces_what_she_can_do(sakhi):
    state = run_general_handler(sakhi.state("namaste", mode="reseller"))

    assert state["reply_text"].startswith("Namaste Sunita Didi didi!")
    for ability in ("catalog items list", "customer queries", "returns handle"):
        assert ability in state["reply_text"]
