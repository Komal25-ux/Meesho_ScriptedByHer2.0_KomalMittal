"""check_pending_selection: the reply to a product picker. The picker is used
up by the next message whatever it is, so a stale picker never lingers."""
import pytest

from backend.core.orchestrator import check_pending_selection
from backend.core.session import PENDING_SELECTIONS
from backend.core.state import _pending_key

from backend.tests.support.sessions import SESSION_A

KEY = _pending_key(SESSION_A, "customer")
PICKER = {"agent": "customer", "options": [{"name": "Red Banarasi Silk Saree"}, {"name": "Blue Georgette Saree"}]}


@pytest.mark.parametrize("reply", [
    "Blue Georgette Saree",
    "  blue georgette saree ",                                                    # case and spaces
    "mujhe ye wala item pasand hai, iski details batao: Blue Georgette Saree",    # a card tap
])
def test_picking_an_option_goes_back_to_the_agent_that_showed_the_picker(sakhi, reply):
    PENDING_SELECTIONS[KEY] = PICKER

    state = check_pending_selection(sakhi.state(reply))

    assert state["pending_selection_route"] == "customer"


@pytest.mark.parametrize("reply", ["Blue Georgette", "koi aur dikhao", "Green Anarkali Suit"])
def test_anything_that_is_not_an_option_abandons_the_picker(sakhi, reply):
    PENDING_SELECTIONS[KEY] = PICKER

    state = check_pending_selection(sakhi.state(reply))

    assert state["pending_selection_route"] == "not_pending"


@pytest.mark.parametrize("reply", ["Blue Georgette Saree", "koi aur dikhao"])
def test_the_picker_is_used_up_either_way(sakhi, reply):
    PENDING_SELECTIONS[KEY] = PICKER

    check_pending_selection(sakhi.state(reply))

    assert KEY not in PENDING_SELECTIONS


def test_a_catalog_picker_routes_back_to_the_catalog_agent(sakhi):
    reseller_key = _pending_key(SESSION_A, "reseller")
    PENDING_SELECTIONS[reseller_key] = dict(PICKER, agent="catalog")

    state = check_pending_selection(sakhi.state("Red Banarasi Silk Saree", mode="reseller"))

    assert state["pending_selection_route"] == "catalog"
