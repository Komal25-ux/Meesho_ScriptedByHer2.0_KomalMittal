"""run_catalog_agent: the reseller asks to list a product; Sakhi drafts it and
waits for her yes. Nothing is saved here - see test_finalize_listing."""
import pytest

from backend.core.agents.catalog import run_catalog_agent
from backend.core.gemini_utils import CatalogCaptionResponse
from backend.core.pricing import suggested_price
from backend.core.session import LAST_REQUESTED_CATEGORY, PENDING_LISTINGS, PENDING_SELECTIONS, SHOWN_PRODUCT_IDS
from backend.core.state import _pending_key

from backend.tests.support.catalog import BLUE_SAREE, RED_SAREE, WHITE_KURTI, YELLOW_SAREE
from backend.tests.support.sessions import SESSION_A

KEY = _pending_key(SESSION_A, "reseller")


def caption(sakhi, price):
    sakhi.gemini.will_return(CatalogCaptionResponse, ui_text=f"✨ Naya maal, sirf ₹{price}!",
                             tts_text=f"नया माल, सिर्फ {price} रुपये!", product_name_tts="नाम")


def draft_for(sakhi, text):
    return run_catalog_agent(sakhi.state(text, mode="reseller"))


def test_naming_a_product_drafts_it_at_the_catalog_price_and_waits(sakhi):
    caption(sakhi, 599)

    state = draft_for(sakhi, RED_SAREE["name"])

    draft = PENDING_LISTINGS[KEY]
    assert draft["selling_price"] == 599 and draft["cost"] == 420
    assert draft["listing_payload"]["whatsapp_caption"] == "✨ Naya maal, sirf ₹599!"
    assert "profit ₹179" in state["reply_text"]
    assert state["reply_text"].endswith("Kya main isey post karun?")
    assert (state["reply_image_url"], state["reply_price"]) == (RED_SAREE["base_image_url"], 599)
    assert sakhi.db.listings == []  # a draft, not a listing


def test_a_product_with_no_catalog_price_is_drafted_with_the_pricing_rule(sakhi):
    sakhi.db.products[RED_SAREE["product_id"]]["suggested_selling_price_inr"] = None

    draft_for(sakhi, RED_SAREE["name"])

    assert PENDING_LISTINGS[KEY]["selling_price"] == suggested_price(420)


@pytest.mark.parametrize("message, price", [
    ("chikankari 799 me", 799),     # her price, above cost (500)
    ("chikankari 501 me", 501),     # one rupee above cost
    ("chikankari 500 me", 715),     # at cost: ignored, catalog price used
    ("chikankari 300 me", 715),     # below cost: ignored
])
def test_a_price_in_her_message_is_used_only_if_it_is_above_cost(sakhi, message, price):
    draft_for(sakhi, message)

    assert PENDING_LISTINGS[KEY]["selling_price"] == price


def test_a_card_tap_to_share_spells_out_cost_price_and_profit(sakhi):
    state = draft_for(sakhi, f"ye item whatsapp group mein share karna hai: {WHITE_KURTI['name']}")

    assert "cost price ₹500" in state["reply_text"]
    assert "₹715 mein post" in state["reply_text"]
    assert "price change karna chahengi" in state["reply_text"]


def test_an_ambiguous_request_shows_a_picker_and_drafts_nothing(sakhi):
    state = draft_for(sakhi, "saree list karni hai")

    assert [o["name"] for o in state["reply_product_options"]] == [RED_SAREE["name"], BLUE_SAREE["name"], YELLOW_SAREE["name"]]
    assert [o["price"] for o in state["reply_product_options"]] == [599, 549, 450]
    assert PENDING_SELECTIONS[KEY]["agent"] == "catalog"
    assert KEY not in PENDING_LISTINGS


def test_a_category_browse_pages_through_without_repeats_until_it_runs_out(sakhi):
    sakhi.classifiers.category = "sarees"
    first = draft_for(sakhi, "sarees dikhao")
    shown = set(SHOWN_PRODUCT_IDS[KEY])

    sakhi.classifiers.category = "same"
    finished = draft_for(sakhi, "aur dikhao")

    assert shown == {RED_SAREE["product_id"], BLUE_SAREE["product_id"], YELLOW_SAREE["product_id"]}
    assert len(first["reply_product_options"]) == 3
    assert "bas itne hi options" in finished["reply_text"]
    assert LAST_REQUESTED_CATEGORY[KEY] == "sarees"


def test_nothing_matching_says_so_and_drafts_nothing(sakhi):
    state = draft_for(sakhi, "jhumka earrings")

    assert "koi kapda ya item nahi mila" in state["reply_text"]
    assert KEY not in PENDING_LISTINGS


def test_with_gemini_down_the_draft_still_has_a_caption_with_the_real_price(sakhi):
    draft_for(sakhi, RED_SAREE["name"])

    posted = PENDING_LISTINGS[KEY]["listing_payload"]["whatsapp_caption"]
    assert "Red Banarasi Silk Saree" in posted and "₹599" in posted
    assert posted.endswith("Order karne ke liye mujhe WhatsApp message karein! 🌸")
