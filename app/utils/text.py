import json
import re
import unicodedata
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def parse_json(text: str, model: type[T]) -> T:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return model.model_validate_json(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return a JSON object") from None
        return model.model_validate(json.loads(text[start : end + 1]))


def normalize_topic(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))
