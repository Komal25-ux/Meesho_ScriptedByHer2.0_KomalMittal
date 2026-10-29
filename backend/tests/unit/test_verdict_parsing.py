import pytest
from typing import Literal
from pydantic import BaseModel

from backend.core.routing.llm_json import parse_verdict


class Verdict(BaseModel):
    intent: Literal["approve", "modify", "new_request"]


@pytest.mark.parametrize("reply", [
    '{"intent": "approve"}',
    '```json\n{"intent": "approve"}\n```',
    '```JSON\n{"intent": "approve"}\n```',
    '```\n{"intent": "approve"}\n```',
    'Sure! Here is the classification: {"intent": "approve"} Hope that helps.',
    '{\n  "intent": "approve"\n}',
])
def test_a_verdict_is_read_from_any_wrapping(reply):
    assert parse_verdict(reply, Verdict) == Verdict(intent="approve")


@pytest.mark.parametrize("reply", [
    None,                          # the call itself failed
    "",
    "approve",                     # no JSON object at all
    '{"intent": approve}',         # broken JSON
    '{"intent": "maybe"}',         # value outside the allowed set
    '{"decision": "approve"}',     # wrong key
    '{"intent": "APPROVE"}',       # Literal values are case-sensitive
])
def test_an_unusable_reply_gives_no_verdict(reply):
    assert parse_verdict(reply, Verdict) is None


CLASSIFIERS = [
    ("backend.core.routing.approval", lambda f: f.classify_approval_intent("x", {}), '{"intent": "modify"}', "modify"),
    ("backend.core.routing.exchange", lambda f: f.classify_exchange_confirmation("x"), '{"intent": "accept"}', "accept"),
    ("backend.core.routing.returns", lambda f: f.classify_return_grievance("x", "Kurti"), '{"scenario": "defective"}', "defective"),
    ("backend.core.routing.category", lambda f: f.extract_category_intent("x", None), '{"category": "suits"}', "suits"),
    ("backend.core.routing.attribute_followup", lambda f: f.classify_attribute_followup("x", "Kurti"), '{"is_followup": true}', True),
    ("backend.core.routing.buying_interest", lambda f: f.classify_buying_interest("x", "Kurti"), '{"interested": true}', True),
]


@pytest.mark.parametrize("module_name, call, reply, expected", CLASSIFIERS, ids=[c[0].rsplit(".", 1)[1] for c in CLASSIFIERS])
def test_every_classifier_trusts_a_fenced_upper_case_verdict_over_its_keywords(monkeypatch, module_name, call, reply, expected):
    import importlib
    module = importlib.import_module(module_name)
    # "x" matches no keyword, so only the verdict can produce `expected`.
    monkeypatch.setattr(module, "generate_with_fallback", lambda *_: f"```JSON\n{reply}\n```")
    assert call(module) == expected
