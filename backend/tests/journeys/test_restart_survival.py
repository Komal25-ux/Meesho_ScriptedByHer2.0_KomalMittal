"""A conversation survives the backend restarting, or moving to another
instance, mid-flow - because its state is in the database, not the process.
The session_state table is the in-memory FakeSessionTable; "restarting" means
replacing the store with a brand-new SupabaseSessionStore over the same table."""
from datetime import timedelta

import pytest

from backend.core import session
from backend.core.agents.returns import run_returns_proactive_outreach
from backend.core.gemini_utils import IntentRouter
from backend.core.session import SupabaseSessionStore

from backend.tests.support.catalog import BLUE_SAREE, PINK_KURTI
from backend.tests.support.fakes import FakeSessionTable
from backend.tests.support.sessions import SESSION_A


@pytest.fixture
def session_table(monkeypatch):
    table = FakeSessionTable()
    monkeypatch.setattr(session, "store", SupabaseSessionStore(table, timedelta(hours=24)))
    return table


def restart(monkeypatch, table):
    monkeypatch.setattr(session, "store", SupabaseSessionStore(table, timedelta(hours=24)))


def test_a_draft_made_before_a_restart_can_be_approved_after_it(sakhi, session_table, monkeypatch):
    sakhi.gemini.will_return(IntentRouter, route_to="CATALOG")
    sakhi.turn(BLUE_SAREE["name"], mode="reseller")

    restart(monkeypatch, session_table)

    sakhi.classifiers.approval = "approve"
    posted = sakhi.turn("haan post kar do", mode="reseller")
    assert posted["listing_finalized"] is True
    assert sakhi.db.listings[0]["product_id"] == BLUE_SAREE["product_id"]


def test_a_return_started_on_one_instance_continues_on_another(sakhi, session_table, monkeypatch):
    with session.session_turn(SESSION_A):
        run_returns_proactive_outreach(SESSION_A, "104", PINK_KURTI["name"])

    restart(monkeypatch, session_table)

    sakhi.classifiers.grievance = "hard_return"
    done = sakhi.turn("paise wapas chahiye")
    assert done["reply_handoff_triggered"] is True
    assert sakhi.db.returns[0]["resolution"] == "refund_forwarded"


def test_each_turn_reads_the_conversation_from_the_database_once(sakhi, session_table):
    sakhi.gemini.will_return(IntentRouter, route_to="GENERAL")
    before = session_table.selects

    sakhi.turn("namaste", mode="customer")

    assert session_table.selects - before == 1
