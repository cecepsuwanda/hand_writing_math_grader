"""Pure string transforms for derivative notation before SymPy parse."""

from __future__ import annotations

import re

# \frac{d}{dx}(...) or \frac{d}{dx}[...]
_DIFF_LATEX_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*'?)\s*=\s*)?\\frac\s*\{\s*d\s*\}\s*\{\s*d(?P<var>[a-zA-Z_]\w*)\s*\}\s*"
    r"(?P<expr>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# d/dx(...) or d/dx ...
_DIFF_ASCII_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*'?)\s*=\s*)?d\s*/\s*d(?P<var>[a-zA-Z_]\w*)\s*"
    r"(?P<expr>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_wrapping(expr: str) -> str:
    cleaned = expr.strip()
    if len(cleaned) >= 2 and cleaned[0] == "(" and cleaned[-1] == ")":
        depth = 0
        for index, char in enumerate(cleaned):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(cleaned) - 1:
                    return cleaned
        return cleaned[1:-1].strip()
    if len(cleaned) >= 2 and cleaned[0] == "[" and cleaned[-1] == "]":
        return cleaned[1:-1].strip()
    return cleaned


def rewrite_derivative_notation(text: str) -> str:
    """Rewrite d/dx forms into ``DIFF(expr, var)`` tokens."""

    def _to_token(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        expr = _strip_wrapping(match.group("expr"))
        return f"DIFF({expr}, {var})"

    cleaned = text.strip()
    cleaned = _DIFF_LATEX_RE.sub(_to_token, cleaned)
    if "DIFF(" not in cleaned:
        cleaned = _DIFF_ASCII_RE.sub(_to_token, cleaned)
    return cleaned
