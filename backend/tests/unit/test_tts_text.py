"""Cleaning text before Sarvam reads it aloud (sanitize_for_tts).

Sarvam's Hindi voice fails or mispronounces on Latin script, emoji and
markdown, so whatever an agent produced is reduced to Devanagari, digits and
basic punctuation, with a few common English words transliterated first."""
import pytest
from hypothesis import given, strategies as st

from backend.core.vaani_audio import sanitize_for_tts


@pytest.mark.parametrize("text, spoken", [
    ("₹599", "599 रुपये"),
    ("₹ 1,299 ka hai", "1,299 रुपये"),          # Latin words dropped, the amount kept
    ("Total profit ₹720", "टोटल प्रॉफिट 720 रुपये"),
    ("Sakhi didi", "सखी दीदी"),
    ("AI Sakhi", "एआई सखी"),
    ("**Saree** 🌸 #offer", "साड़ी"),
])
def test_what_sarvam_is_given(text, spoken):
    assert sanitize_for_tts(text) == spoken


def test_devanagari_and_its_punctuation_pass_through_unchanged():
    text = "नमस्ते दीदी! आपकी साड़ी 599 रुपये में है।"
    assert sanitize_for_tts(text) == text


def test_transliteration_matches_whole_words_only():
    # "sales" becomes सेल्स; "wholesale" is not a known word and is dropped,
    # rather than becoming "whole" + सेल्स.
    assert sanitize_for_tts("sales") == "सेल्स"
    assert sanitize_for_tts("wholesale") == ""


@given(st.text())
def test_no_latin_letters_or_symbols_ever_reach_sarvam(text):
    spoken = sanitize_for_tts(text)
    assert not any("a" <= c.lower() <= "z" for c in spoken)
    allowed = set("0123456789 ,.?!।॥")
    assert all(c in allowed or "ऀ" <= c <= "ॿ" for c in spoken)
    assert spoken == spoken.strip() and "  " not in spoken
