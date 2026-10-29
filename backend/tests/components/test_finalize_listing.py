"""finalize_catalog_listing: her yes turns the draft into a live listing and
broadcasts it to the buyer side of the same session."""
import pytest

from backend.core.orchestrator import finalize_catalog_listing
from backend.core.session import FRESH_BROADCAST_LOCK, LAST_VIEWED_PRODUCT, PENDING_LISTINGS
from backend.core.state import _pending_key
from backend.errors import DependencyUnavailable

from backend.tests.support.catalog import GREEN_SUIT
from backend.tests.support.sessions import SESSION_A

RESELLER = _pending_key(SESSION_A, "reseller")
BUYER = _pending_key(SESSION_A, "customer")


def a_draft(price=1150):
    return {
        "matched_product_name": "Green Anarkali Suit", "selling_price": price, "cost": 700,
        "base_image_url": GREEN_SUIT["base_image_url"], "whatsapp_caption_tts": "ग्रीन अनारकली सूट",
        "listing_payload": {"reseller_id": "reseller-1", "product_id": GREEN_SUIT["product_id"],
                            "product_name": "Green Anarkali Suit", "category": "suits",
                            "selling_price_inr": price, "cost_price_inr": 700,
                            "whatsapp_caption": "Green Anarkali Suit ₹1150"},
        "matched_product": GREEN_SUIT,
    }


def test_approving_saves_the_listing_exactly_as_drafted(sakhi):
    PENDING_LISTINGS[RESELLER] = a_draft()

    state = finalize_catalog_listing(sakhi.state("haan", mode="reseller"))

    [listing] = sakhi.db.listings
    assert (listing["selling_price_inr"], listing["whatsapp_caption"]) == (1150, "Green Anarkali Suit ₹1150")
    assert listing["image_url"] == GREEN_SUIT["base_image_url"]
    assert RESELLER not in PENDING_LISTINGS
    assert "live post ho gaya" in state["reply_text"] and "profit ₹450" in state["reply_text"]


def test_the_post_is_broadcast_with_its_own_caption_and_voice_text(sakhi):
    PENDING_LISTINGS[RESELLER] = a_draft()

    state = finalize_catalog_listing(sakhi.state("haan", mode="reseller"))

    assert state["listing_finalized"] is True
    assert state["listing_broadcast_caption"] == "Green Anarkali Suit ₹1150"
    assert state["listing_broadcast_caption_tts"] == "ग्रीन अनारकली सूट"
    assert (state["listing_product_name"], state["listing_category"]) == ("Green Anarkali Suit", "suits")


def test_the_buyer_side_is_primed_with_the_price_she_set_not_the_catalog_price(sakhi):
    PENDING_LISTINGS[RESELLER] = a_draft(price=1150)   # catalog says 1000

    finalize_catalog_listing(sakhi.state("haan", mode="reseller"))

    assert LAST_VIEWED_PRODUCT[BUYER]["suggested_selling_price_inr"] == 1150
    assert FRESH_BROADCAST_LOCK[BUYER] is True


def test_approving_with_no_draft_says_so_and_saves_nothing(sakhi):
    state = finalize_catalog_listing(sakhi.state("haan", mode="reseller"))

    assert "pichla draft nahi mil raha" in state["reply_text"]
    assert sakhi.db.listings == []


def test_a_failed_save_keeps_the_draft_and_announces_nothing(sakhi):
    PENDING_LISTINGS[RESELLER] = a_draft()
    sakhi.db.fail("save_listing")

    with pytest.raises(DependencyUnavailable):
        finalize_catalog_listing(sakhi.state("haan", mode="reseller"))

    assert PENDING_LISTINGS[RESELLER] == a_draft()
    assert BUYER not in FRESH_BROADCAST_LOCK
