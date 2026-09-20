"""Pure string transforms for absolute-value notation before SymPy parse."""

from __future__ import annotations

import re


_LVERT_RE = re.compile(
    r"\\lvert\s*(.*?)\s*\\rvert",
    re.IGNORECASE | re.DOTALL,
)
_ABS_CMD_RE = re.compile(
    r"\\abs\s*\{([^{}]*)\}",
    re.IGNORECASE,
)
_LEFT_RIGHT_BAR_RE = re.compile(
    r"\\left\s*\|\s*(.*?)\s*\\right\s*\|",
    re.IGNORECASE | re.DOTALL,
)
# Plain |...| after LaTeX left/right abs forms are rewritten.
_PLAIN_ABS_RE = re.compile(r"\|([^|]+)\|")


def rewrite_abs_notation(text: str) -> str:
    """Rewrite absolute-value LaTeX/ASCII into ``Abs(...)`` tokens."""
    cleaned = text
    cleaned = _LVERT_RE.sub(r"Abs(\1)", cleaned)
    cleaned = _ABS_CMD_RE.sub(r"Abs(\1)", cleaned)
    cleaned = _LEFT_RIGHT_BAR_RE.sub(r"Abs(\1)", cleaned)
    cleaned = _PLAIN_ABS_RE.sub(r"Abs(\1)", cleaned)
    return cleaned
