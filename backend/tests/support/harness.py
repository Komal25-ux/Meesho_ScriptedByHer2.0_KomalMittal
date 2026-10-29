"""Runs Sakhi's real graph and agents against the fakes in fakes.py."""
import sys
from types import ModuleType
from typing import Any

from backend.core import gemini_utils
from backend.core.orchestrator import sakhi_orchestrator
from backend.core.routing import (
    approval, attribute_followup, buying_interest, category, exchange, returns,
)
from backend.core.session import session_turn
from backend.core.state import new_turn_state
from backend.db.supabase_client import db_client

from backend.tests.support.fakes import Classifiers, FakeSupabase, ScriptedGemini, fake_embedding
from backend.tests.support.sessions import DEMO_NUMBER, SESSION_A


def _replace_everywhere(monkeypatch, original: Any, replacement: Any) -> None:
    """Swap `original` for `replacement` in every backend module that holds a
    reference to it. Modules import these helpers by name, so patching the
    defining module alone would miss the copies."""
    for module in list(sys.modules.values()):
        if not isinstance(module, ModuleType) or not module.__name__.startswith("backend."):
            continue
        if module.__name__.startswith("backend.tests"):
            continue
        for name, value in list(vars(module).items()):
            if value is original:
                monkeypatch.setattr(module, name, replacement)


def _no_free_text_calls(*_args, **_kwargs):
    raise AssertionError("unexpected free-text Gemini call: the classifiers are scripted in these tests")


class Sakhi:
    def __init__(self, gemini: ScriptedGemini, classifiers: Classifiers, db: FakeSupabase):
        self.gemini = gemini
        self.classifiers = classifiers
        self.db = db

    def state(self, text: str, mode: str = "customer", session: str = SESSION_A) -> dict:
        """A turn's state as it looks after load_memory, for calling one node directly."""
        state = new_turn_state(session, DEMO_NUMBER, text, active_mode=mode)
        reseller = self.db.RESELLER
        state.update(reseller_id=reseller["id"], reseller_name=reseller["name"], reseller_location=reseller["location"])
        return state

    def turn(self, text: str, mode: str = "customer", session: str = SESSION_A, message_id: str = None) -> dict:
        """One full message through the compiled graph, as /chat/send runs it."""
        with session_turn(session):
            return sakhi_orchestrator.invoke(
                new_turn_state(session, DEMO_NUMBER, text, active_mode=mode, client_message_id=message_id)
            )


def install(monkeypatch, products) -> Sakhi:
    gemini, classifiers, db = ScriptedGemini(), Classifiers(), FakeSupabase(products)

    _replace_everywhere(monkeypatch, gemini_utils.generate_structured_with_fallback, gemini.structured)
    _replace_everywhere(monkeypatch, gemini_utils.generate_with_fallback, _no_free_text_calls)
    _replace_everywhere(monkeypatch, gemini_utils.embed_content_with_fallback, fake_embedding)
    for original in (
        approval.classify_approval_intent, attribute_followup.classify_attribute_followup,
        buying_interest.classify_buying_interest, category.extract_category_intent,
        exchange.classify_exchange_confirmation, returns.classify_return_grievance,
    ):
        _replace_everywhere(monkeypatch, original, getattr(classifiers, original.__name__))
    for method in FakeSupabase.METHODS:
        monkeypatch.setattr(db_client, method, getattr(db, method))
    return Sakhi(gemini, classifiers, db)
