"""Pure string transforms for integral notation before SymPy parse."""

from __future__ import annotations

import re

# \int_{a}^{b} expr \,dx  (optional L = prefix)
_INT_DEFINITE_LATEX_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?\\int\s*_\s*\{\s*(?P<lower>[^}]+?)\s*\}\s*"
    r"\^\s*\{\s*(?P<upper>[^}]+?)\s*\}\s*"
    r"(?P<expr>.+?)(?:\\,)?\s*d(?P<var>[a-zA-Z_]\w*)\s*$",
    re.IGNORECASE | re.DOTALL,
)

# \int expr \,dx
_INT_INDEFINITE_LATEX_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?\\int\s*"
    r"(?P<expr>.+?)(?:\\,)?\s*d(?P<var>[a-zA-Z_]\w*)\s*$",
    re.IGNORECASE | re.DOTALL,
)

# int_a^b expr dx
_INT_DEFINITE_ASCII_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?int\s*_\s*(?P<lower>[^\s^]+)\s*"
    r"\^\s*(?P<upper>\S+)\s+"
    r"(?P<expr>.+?)\s+d(?P<var>[a-zA-Z_]\w*)\s*$",
    re.IGNORECASE | re.DOTALL,
)

# int expr dx
_INT_INDEFINITE_ASCII_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?int\s+"
    r"(?P<expr>.+?)\s+d(?P<var>[a-zA-Z_]\w*)\s*$",
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


def rewrite_integral_notation(text: str) -> str:
    """Rewrite integral forms into ``INT(expr, var)`` or ``INT(expr, var, a, b)``."""

    def _indefinite(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        expr = _strip_wrapping(match.group("expr"))
        return f"INT({expr}, {var})"

    def _definite(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        expr = _strip_wrapping(match.group("expr"))
        lower = match.group("lower").strip()
        upper = match.group("upper").strip()
        return f"INT({expr}, {var}, {lower}, {upper})"

    cleaned = text.strip()
    if re.search(r"\\int\s*_", cleaned, re.IGNORECASE):
        updated = _INT_DEFINITE_LATEX_RE.sub(_definite, cleaned)
        if updated != cleaned:
            return updated
    if "\\int" in cleaned.lower() or "\\INT" in cleaned:
        updated = _INT_INDEFINITE_LATEX_RE.sub(_indefinite, cleaned)
        if "INT(" in updated:
            return updated
        cleaned = updated

    if re.match(r"(?:[A-Za-z]\w*\s*=\s*)?int\s*_", cleaned, re.IGNORECASE):
        updated = _INT_DEFINITE_ASCII_RE.sub(_definite, cleaned)
        if "INT(" in updated:
            return updated
    updated = _INT_INDEFINITE_ASCII_RE.sub(_indefinite, cleaned)
    return updated
