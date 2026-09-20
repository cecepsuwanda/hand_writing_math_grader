"""Pure string transforms for limit notation before SymPy parse."""

from __future__ import annotations

import re

# \lim_{x \to a} expr   optional L = prefix; optional a^+ / a^-
_LIM_LATEX_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?\\lim\s*_\s*\{\s*"
    r"(?P<var>[a-zA-Z_]\w*)\s*(?:\\to|->|→)\s*"
    r"(?P<point>[^}^+\-]+?)(?P<side>\^\s*[\+\-]|[\+\-])?\s*\}\s*"
    r"(?P<expr>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# lim x->a expr
_LIM_ASCII_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?lim\s+"
    r"(?P<var>[a-zA-Z_]\w*)\s*(?:->|→|\\to)\s*"
    r"(?P<point>[^\s+\-]+?)(?P<side>[\+\-])?\s+"
    r"(?P<expr>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_side(side: str | None) -> str:
    if not side:
        return "+-"
    cleaned = side.replace("^", "").strip()
    if cleaned.startswith("+"):
        return "+"
    if cleaned.startswith("-"):
        return "-"
    return "+-"


def rewrite_limit_notation(text: str) -> str:
    """Rewrite lim forms into ``LIMIT(expr, var, point, dir)`` tokens."""

    def _to_token(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        point = match.group("point").strip()
        expr = match.group("expr").strip()
        direction = _normalize_side(match.group("side"))
        # Keep assign prefix out; LIMIT token is the whole step value.
        return f"LIMIT({expr}, {var}, {point}, {direction})"

    cleaned = text.strip()
    cleaned = _LIM_LATEX_RE.sub(_to_token, cleaned)
    if "LIMIT(" not in cleaned:
        cleaned = _LIM_ASCII_RE.sub(_to_token, cleaned)
    return cleaned
