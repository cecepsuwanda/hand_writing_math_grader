"""Sign-chart patterns (``+ - +``) from key rows, student rows and figure captions (pure)."""

from __future__ import annotations

import re
from collections.abc import Iterable

# ``f(a) = ... < 0``: an evaluation row whose trailing relation gives the sign.
_EVAL_ROW_SIGN_RE = re.compile(r"=.*?([<>])\s*0\s*$")

# Standalone sign marks (``-1`` / ``x-3`` are numbers or algebra, not signs).
_CAPTION_SIGN_RE = re.compile(
    r"(?<![\w])([+\-\u2212]{1,2})(?![\w])"
    r"|\b(plus|positi(?:f|ve)|minus|negati(?:f|ve))\b",
    re.IGNORECASE,
)

_WORD_SIGNS = {"plus": "+", "positif": "+", "positive": "+"}


def evaluation_row_signs(rows: Iterable[str]) -> list[str]:
    """Signs of ``f(a) = value < 0`` / ``> 0`` rows in order; other rows are skipped."""
    signs: list[str] = []
    for row in rows:
        match = _EVAL_ROW_SIGN_RE.search((row or "").strip())
        if match:
            signs.append("+" if match.group(1) == ">" else "-")
    return signs


def caption_signs(caption: str) -> list[str]:
    """Sign marks read left to right; ``++`` written over one interval counts once."""
    signs: list[str] = []
    for match in _CAPTION_SIGN_RE.finditer(caption or ""):
        mark, word = match.group(1), match.group(2)
        if mark:
            signs.append("+" if mark[0] == "+" else "-")
        else:
            signs.append(_WORD_SIGNS.get(word.lower(), "-"))
    return signs


def format_signs(signs: list[str]) -> str:
    return " ".join(signs)
