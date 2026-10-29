import pytest
from hypothesis import given, strategies as st

from backend.core.routing.keywords import mentions


@pytest.mark.parametrize("text, phrase, expected", [
    ("haan ok", "ok", True),
    ("Ok!", "ok", True),               # case and punctuation around the word
    ("(haan)", "haan", True),
    ("book kar do", "ok", False),      # the substring bug: "ok" inside "book"
    ("address badalna hai", "dress", False),
    ("laptop", "top", False),
    ("orange", "rang", False),
    ("theek hai", "theek hai", True),  # multi-word phrase
    ("theek    hai", "theek hai", False),
    ("sarees dikhao", "saree*", True), # prefix phrase
    ("dosaree", "saree*", False),      # prefix still has to start a word
    ("saree", "saree*", True),
])
def test_mentions_matches_whole_words_or_word_prefixes(text, phrase, expected):
    assert mentions(text, [phrase]) is expected


def test_mentions_is_false_for_no_phrases():
    assert mentions("haan", []) is False


@given(word=st.from_regex(r"[a-z]{2,10}", fullmatch=True),
       before=st.sampled_from(["", "haan ", "(", "kal "]),
       after=st.sampled_from(["", " hai", "!", "?"]))
def test_a_word_is_always_found_when_it_stands_alone(word, before, after):
    assert mentions(f"{before}{word}{after}", [word])


@given(word=st.from_regex(r"[a-z]{2,6}", fullmatch=True), glue=st.from_regex(r"[a-z]{1,4}", fullmatch=True))
def test_a_word_is_never_found_inside_a_longer_word(word, glue):
    assert not mentions(f"{glue}{word}{glue}", [word])
