"""Keyword matching for the classifiers' outage fallbacks.

These only run when Gemini is unreachable, but they used plain substring
checks, which matched inside other words: "ok" in "book", "dress" in
"address", "top" in "stop" and "laptop", "rang" in "orange". Phrases now
match whole words. A phrase ending in "*" matches as a word prefix instead,
for stems that take endings ("saree*" covers "sarees", "fit*" covers
"fitting").
"""
import re
from functools import lru_cache
from typing import Iterable

__all__ = ["mentions"]


@lru_cache(maxsize=None)
def _pattern(phrase: str) -> "re.Pattern[str]":
    if phrase.endswith("*"):
        return re.compile(r"\b" + re.escape(phrase[:-1].lower()))
    return re.compile(r"\b" + re.escape(phrase.lower()) + r"\b")


def mentions(text: str, phrases: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(_pattern(phrase).search(lowered) for phrase in phrases)
