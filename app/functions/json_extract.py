"""Pure helpers to extract JSON objects from model text."""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
    re.DOTALL | re.IGNORECASE,
)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object from raw model output.

    Raises:
        ValueError: if no valid JSON object can be parsed.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("empty model response")

    candidates: list[str] = []
    match = _FENCE_RE.search(cleaned)
    if match:
        candidates.append(match.group(1))
    candidates.append(cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start : end + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        last_error = ValueError(f"expected JSON object, got {type(parsed).__name__}")

    if last_error is not None:
        raise ValueError(str(last_error)) from last_error
    raise ValueError("no JSON object found in model response")
