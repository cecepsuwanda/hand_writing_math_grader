"""Pure string transform: indexed roots ``x_1``, ``x_{2}``, ``x₁`` → the variable."""

from __future__ import annotations

import re

# A lone letter (not the tail of a command such as ``\log_2``) with a numeric index.
_UNDERSCORE_INDEX_RE = re.compile(
    r"(?<![A-Za-z\\])([A-Za-z])\s*_\s*(?:\{\s*\d+\s*\}|\d+)"
)
_UNICODE_INDEX_RE = re.compile(r"(?<![A-Za-z\\])([A-Za-z])[₀-₉]+")


def rewrite_indexed_roots(text: str) -> str:
    """``x_1 = 2 or x_{2} = 3`` → ``x = 2 or x = 3`` (roots named by index).

    Bare ``x1`` is left alone: it cannot be told apart from ``x*1``.
    """
    cleaned = _UNDERSCORE_INDEX_RE.sub(r"\1", text)
    return _UNICODE_INDEX_RE.sub(r"\1", cleaned)
