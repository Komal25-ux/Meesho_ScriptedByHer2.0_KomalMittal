from backend.core.gemini_utils import embed_content_with_fallback

__all__ = ["_embed_text"]


def _embed_text(text: str) -> list:
    return embed_content_with_fallback(text, task_type="retrieval_query", output_dimensionality=768)
