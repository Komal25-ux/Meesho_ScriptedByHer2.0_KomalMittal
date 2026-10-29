"""The Gemini client's fallback chain (backend/core/gemini_utils.py).

Order of attempts: every model in the chain on the current key, then the next
key from the first model again. A per-model error (quota, 429, overload)
moves to the next model; a key-level error (403, invalid key) abandons the
key at once, since every model would fail the same way.

The google-genai client is replaced by a fake that records (key, model) for
every call and answers according to a plan.
"""
import pytest

from backend.core import gemini_utils
from backend.core.gemini_utils import AgentResponse
from backend.errors import DependencyUnavailable


class FakeGenAI:
    def __init__(self, plan):
        self.plan = plan          # (key, model) -> reply text, or raises
        self.calls = []

    def __call__(self, api_key):  # stands in for genai.Client(api_key=...)
        fake = self

        class Models:
            def generate_content(self, model, contents, config=None):
                fake.calls.append((api_key, model))
                return type("Reply", (), {"text": fake.plan(api_key, model)})()

            def embed_content(self, model, contents, config=None):
                fake.calls.append((api_key, model))
                values = fake.plan(api_key, model)
                return type("Reply", (), {"embeddings": [type("E", (), {"values": values})()]})()

        return type("Client", (), {"models": Models()})()


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(gemini_utils.settings, "GEMINI_API_KEY", "KEY_A")
    monkeypatch.setattr(gemini_utils.settings, "GEMINI_API_KEY_FALLBACK", "KEY_B")
    monkeypatch.setattr(gemini_utils.settings, "GEMINI_API_KEY_FALLBACK_2", "")
    monkeypatch.setattr(gemini_utils.settings, "GEMINI_MODEL", "m1")
    monkeypatch.setattr(gemini_utils.settings, "GEMINI_FALLBACK_MODELS", "m2, m3,m1")
    monkeypatch.setattr(gemini_utils, "_CURRENT_KEY_INDEX", 0)

    def install(plan):
        fake = FakeGenAI(plan)
        monkeypatch.setattr(gemini_utils.genai, "Client", lambda api_key: fake(api_key))
        return fake
    return install


def test_the_model_chain_is_the_primary_then_the_fallbacks_without_repeats(gemini):
    assert gemini_utils._model_chain() == ["m1", "m2", "m3"]


def test_the_first_model_that_answers_wins(gemini):
    fake = gemini(lambda key, model: "Namaste")

    assert gemini_utils.generate_with_fallback("hi") == "Namaste"
    assert fake.calls == [("KEY_A", "m1")]


def test_a_quota_error_moves_to_the_next_model_on_the_same_key(gemini):
    def plan(key, model):
        if model == "m1":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "from m2"
    fake = gemini(plan)

    assert gemini_utils.generate_with_fallback("hi") == "from m2"
    assert fake.calls == [("KEY_A", "m1"), ("KEY_A", "m2")]


def test_a_bad_key_is_abandoned_at_once_for_the_next_key(gemini):
    def plan(key, model):
        if key == "KEY_A":
            raise RuntimeError("403 PERMISSION_DENIED: API key invalid")
        return "from key B"
    fake = gemini(plan)

    assert gemini_utils.generate_with_fallback("hi") == "from key B"
    assert fake.calls == [("KEY_A", "m1"), ("KEY_B", "m1")]   # m2/m3 on KEY_A never tried


def test_an_empty_reply_counts_as_no_answer(gemini):
    fake = gemini(lambda key, model: "" if model == "m1" else "from m2")

    assert gemini_utils.generate_with_fallback("hi") == "from m2"


def test_when_everything_fails_the_caller_gets_none(gemini):
    def plan(key, model):
        raise RuntimeError("503 overloaded")
    fake = gemini(plan)

    assert gemini_utils.generate_with_fallback("hi") is None
    assert len(fake.calls) == 6   # 3 models x 2 keys, each tried once


def test_the_key_index_wraps_around(gemini):
    gemini(lambda key, model: "ok")
    seen = []
    for _ in range(3):
        seen.append(gemini_utils._get_gemini_keys()[gemini_utils._CURRENT_KEY_INDEX])
        gemini_utils.rotate_gemini_key()

    assert seen == ["KEY_A", "KEY_B", "KEY_A"]


def test_placeholder_keys_are_not_keys(gemini, monkeypatch):
    monkeypatch.setattr(gemini_utils.settings, "GEMINI_API_KEY_FALLBACK", "YOUR_GEMINI_KEY_HERE")
    assert gemini_utils._get_gemini_keys() == ["KEY_A"]


# ── structured output ────────────────────────────────────────────────

def test_a_structured_reply_is_validated_against_its_schema(gemini):
    gemini(lambda key, model: '{"ui_text": "Namaste", "tts_text": "नमस्ते"}')

    assert gemini_utils.generate_structured_with_fallback("hi", AgentResponse) == AgentResponse(
        ui_text="Namaste", tts_text="नमस्ते")


def test_a_reply_that_does_not_fit_the_schema_moves_to_the_next_model(gemini):
    fake = gemini(lambda key, model: '{"wrong": 1}' if model == "m1" else '{"ui_text": "ok", "tts_text": "ठीक"}')

    assert gemini_utils.generate_structured_with_fallback("hi", AgentResponse).ui_text == "ok"
    assert fake.calls[:2] == [("KEY_A", "m1"), ("KEY_A", "m2")]


def test_no_structured_answer_anywhere_gives_none(gemini):
    gemini(lambda key, model: "not json")

    assert gemini_utils.generate_structured_with_fallback("hi", AgentResponse) is None


# ── embeddings ───────────────────────────────────────────────────────

def test_an_embedding_is_the_768_values_from_the_first_working_key(gemini):
    gemini(lambda key, model: [0.25] * 768)

    assert gemini_utils.embed_content_with_fallback("laal saree") == [0.25] * 768


def test_an_empty_query_needs_no_embedding_call(gemini):
    fake = gemini(lambda key, model: [0.25] * 768)

    assert gemini_utils.embed_content_with_fallback("   ") == []
    assert fake.calls == []


def test_an_embedding_failure_on_every_key_is_raised_not_returned_as_empty(gemini):
    def plan(key, model):
        raise RuntimeError("503 overloaded")
    fake = gemini(plan)

    with pytest.raises(DependencyUnavailable):
        gemini_utils.embed_content_with_fallback("laal saree")
    assert [key for key, _ in fake.calls] == ["KEY_A", "KEY_B"]
