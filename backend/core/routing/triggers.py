from backend.core.constants import CATALOG_SHARE_TRIGGER_RE, CUSTOMER_DETAILS_TRIGGER_RE

__all__ = ["_strip_trigger_prefix"]


def _strip_trigger_prefix(text: str) -> str:
    """Strips a recognized Product Card Click trigger prefix (either one),
    returning just the product name that followed it. Returns `text`
    unchanged if neither prefix matches, so this is always safe to call."""
    for pattern in (CATALOG_SHARE_TRIGGER_RE, CUSTOMER_DETAILS_TRIGGER_RE):
        match = pattern.match(text)
        if match:
            return text[match.end():].strip()
    return text
