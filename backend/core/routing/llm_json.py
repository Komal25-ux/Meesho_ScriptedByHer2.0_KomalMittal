"""Reading a classifier's JSON verdict out of a Gemini reply."""
import re
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

__all__ = ["parse_verdict"]

T = TypeVar("T", bound=BaseModel)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict(raw_text: Optional[str], model: Type[T]) -> Optional[T]:
    """The reply's JSON object validated against `model`, or None when there
    isn't a usable one - no reply at all (outage), no object in it, broken
    JSON, or a value outside the allowed set. Code fences and any text
    around the object are ignored, in whatever case the model writes them
    (the six copies this replaces only knew a lower-case ```json fence)."""
    if not raw_text:
        return None
    match = _JSON_OBJECT.search(raw_text)
    if not match:
        return None
    try:
        return model.model_validate_json(match.group(0))
    except ValidationError:
        return None
