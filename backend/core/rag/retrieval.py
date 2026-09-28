from typing import Optional, Dict, Any

from backend.db.supabase_client import db_client
from backend.core.rag.embeddings import _embed_text

__all__ = ["_lookup_product_by_name", "_find_alternative_product"]


def _lookup_product_by_name(product_name: str) -> Optional[Dict[str, Any]]:
    """Anchors the Returns Retention flow to the actual item being returned by
    semantic-matching its name against the real catalog - never guessed."""
    matches = db_client.match_products(_embed_text(product_name), threshold=0.15, limit=1)
    return matches[0] if matches else None


def _find_alternative_product(original_product: Dict[str, Any], query_hint: str) -> Optional[Dict[str, Any]]:
    """Scenario B/C alternative lookup: real RAG retrieval against the catalog
    only - the model is never allowed to name a product it wasn't given.
    query_hint biases the search toward the customer's actual complaint, and
    the original product is excluded from its own results by product_id."""
    matches = db_client.match_products(
        _embed_text(f"{original_product.get('category', '')} {query_hint}"),
        threshold=0.15,
        limit=3
    )
    for m in matches:
        if m.get("product_id") != original_product.get("product_id"):
            return m
    return None
