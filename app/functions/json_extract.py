"""Pure helpers to extract JSON objects from model text."""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
    re.DOTALL | re.IGNORECASE,
)

_HEX = "0123456789abcdefABCDEF"

# Multi-letter LaTeX names that collide with JSON ``\b``/``\f``/``\n``/``\r``/``\t``.
_LATEX_JSON_COLLISIONS = frozenset(
    {
        "bar",
        "begin",
        "beta",
        "big",
        "binom",
        "mathbb",
        "mathbf",
        "mathrm",
        "bigcap",
        "bigcup",
        "frac",
        "forall",
        "lfloor",
        "rceil",
        "nabla",
        "natural",
        "ne",
        "neq",
        "newline",
        "nexists",
        "ni",
        "nmid",
        "not",
        "notin",
        "nu",
        "rangle",
        "rho",
        "right",
        "rightarrow",
        "tan",
        "text",
        "therefore",
        "theta",
        "times",
        "to",
        "triangle",
    }
)


def repair_json_escapes(text: str) -> str:
    """Escape bare backslashes inside JSON strings (common with LaTeX from LLMs).

    Keeps real JSON escapes. Turns invalid escapes (``\\infty``, ``\\leq``) and
    LaTeX collisions (``\\frac``, ``\\neq``, ``\\times``) into doubled backslashes.
    """
    result: list[str] = []
    in_string = False
    i = 0
    length = len(text)

    while i < length:
        char = text[i]
        if not in_string:
            result.append(char)
            if char == '"':
                in_string = True
            i += 1
            continue

        if char == '"':
            result.append(char)
            in_string = False
            i += 1
            continue

        if char != "\\":
            result.append(char)
            i += 1
            continue

        if i + 1 >= length:
            result.append("\\\\")
            i += 1
            continue

        nxt = text[i + 1]
        if nxt in '"\\/':
            result.append("\\")
            result.append(nxt)
            i += 2
            continue

        if nxt == "u" and i + 5 < length and all(
            c in _HEX for c in text[i + 2 : i + 6]
        ):
            result.append(text[i : i + 6])
            i += 6
            continue

        if nxt.isalpha():
            end = i + 1
            while end < length and text[end].isalpha():
                end += 1
            run = text[i + 1 : end]
            if run in _LATEX_JSON_COLLISIONS:
                result.append("\\\\")
                i += 1
                continue
            if run[0] in "bfnrt":
                # Real JSON escape, even when glued to text (``\nline2``).
                result.append("\\")
                result.append(run[0])
                i += 2
                continue
            # Invalid / LaTeX (``\infty``, ``\leq``, ``\in``, ``\sin``, …).
            result.append("\\\\")
            i += 1
            continue

        # Invalid escape (``\ ``, ``\{``, digits, …).
        result.append("\\\\")
        i += 1

    return "".join(result)


_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_SMART_DOUBLE_QUOTES = str.maketrans(
    {
        "\u201c": '"',  # “
        "\u201d": '"',  # ”
        "\u201e": '"',  # „
        "\u00ab": '"',  # «
        "\u00bb": '"',  # »
    }
)

_STATUS_RE = re.compile(
    r'"status"\s*:\s*"(?P<status>valid|invalid|uncertain)"',
    re.IGNORECASE,
)
_CONFIDENCE_RE = re.compile(
    r'"confidence"\s*:\s*(?P<conf>-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)',
)
_REASON_KEY_RE = re.compile(r'"reason"\s*:\s*"', re.IGNORECASE)
_REASON_END_BEFORE_CONF_RE = re.compile(
    r'"\s*,\s*"confidence"',
    re.IGNORECASE,
)


def repair_llm_json_syntax(text: str) -> str:
    """Fix common LLM JSON syntax issues (trailing commas, smart quotes)."""
    cleaned = text.translate(_SMART_DOUBLE_QUOTES)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _TRAILING_COMMA_RE.sub(r"\1", cleaned)
    return cleaned


def _unescape_salvaged_text(text: str) -> str:
    """Unescape a raw JSON string slice without eating LaTeX commands.

    ``\\\\neq`` becomes ``\\neq``. A lone ``\\n`` becomes a newline. ``\\neq``
    and ``\\not`` stay intact (they are not the JSON newline escape).
    """
    result: list[str] = []
    simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "\\" or index + 1 >= length:
            result.append(char)
            index += 1
            continue
        nxt = text[index + 1]
        if nxt == "\\":
            result.append("\\")
            index += 2
            continue
        if nxt == '"':
            result.append('"')
            index += 2
            continue
        if nxt in simple and (index + 2 >= length or not text[index + 2].isalpha()):
            result.append(simple[nxt])
            index += 2
            continue
        result.append("\\")
        index += 1
    return "".join(result)


def salvage_judgement_object(text: str) -> dict[str, Any] | None:
    """Best-effort extract of ``status`` / ``reason`` / ``confidence`` from broken JSON.

    Handles unescaped double quotes inside ``reason`` by scanning until
    ``", "confidence"`` (or the last ``"}``). Returns ``None`` if status is missing.
    """
    if not re.search(r'"status"', text, re.IGNORECASE):
        return None
    if not re.search(r'"reason"', text, re.IGNORECASE):
        return None

    status_match = _STATUS_RE.search(text)
    if status_match is None:
        return None
    status = status_match.group("status").lower()

    conf_match = _CONFIDENCE_RE.search(text)
    confidence: float | None = None
    if conf_match is not None:
        try:
            confidence = float(conf_match.group("conf"))
        except ValueError:
            confidence = None

    reason = ""
    reason_key = _REASON_KEY_RE.search(text)
    if reason_key is not None:
        start = reason_key.end()
        end_match = _REASON_END_BEFORE_CONF_RE.search(text, start)
        if end_match is not None:
            reason = text[start : end_match.start()]
        else:
            # Fallback: until last " before closing brace
            end = text.rfind('"')
            brace = text.rfind("}")
            if brace != -1 and end != -1 and end < brace:
                reason = text[start:end]
            else:
                reason = text[start:].rstrip().rstrip("}").rstrip().rstrip('"')

    reason = _unescape_salvaged_text(reason)

    payload: dict[str, Any] = {"status": status, "reason": reason.strip()}
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


_THINK_BLOCK_RE = re.compile(
    r"<think>.*?</think>"
    r"|<\|channel\>thought\n.*?<channel\|>"
    r"|<\|think\|>.*?(?=\{|$)",
    re.DOTALL | re.IGNORECASE,
)


def _strip_thinking_wrappers(text: str) -> str:
    """Remove common model thinking / channel wrappers before JSON parse."""
    cleaned = text.lstrip("\ufeff").strip()
    cleaned = _THINK_BLOCK_RE.sub("", cleaned).strip()
    return cleaned


def _response_preview(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object from raw model output.

    Raises:
        ValueError: if no valid JSON object can be parsed.
    """
    cleaned = _strip_thinking_wrappers(text)
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
    seen: set[str] = set()
    for candidate in candidates:
        syntax_fixed = repair_llm_json_syntax(candidate)
        # Prefer repaired text so ``\frac`` is not silently read as form-feed.
        attempts = (
            repair_json_escapes(syntax_fixed),
            syntax_fixed,
            repair_json_escapes(candidate),
            candidate,
        )
        for attempt in attempts:
            if attempt in seen:
                continue
            seen.add(attempt)
            try:
                parsed = json.loads(attempt)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(parsed, dict):
                return parsed
            last_error = ValueError(
                f"expected JSON object, got {type(parsed).__name__}"
            )

    preview = _response_preview(cleaned)
    if last_error is not None:
        raise ValueError(f"{last_error}; response_preview={preview!r}") from last_error
    raise ValueError(f"no JSON object found in model response; response_preview={preview!r}")
