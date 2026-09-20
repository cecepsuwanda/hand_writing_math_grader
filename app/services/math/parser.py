"""Normalize and parse student math strings into SymPy relations."""

from __future__ import annotations

import re

from sympy import Eq, Expr, Ge, Gt, Le, Lt, Ne, Symbol
from sympy.core.relational import Relational
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from app.exceptions import MathParseError

_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

_FINAL_ANSWER_PREFIX_RE = re.compile(
    r"^(?:jawaban\s+akhir|final\s+answer|langkah)\s*[:：-]?\s*",
    re.IGNORECASE,
)

_LATEX_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\\leq|\\le\b"), "<="),
    (re.compile(r"\\geq|\\ge\b"), ">="),
    (re.compile(r"\\neq|\\ne\b"), "!="),
    (re.compile(r"\\lt\b"), "<"),
    (re.compile(r"\\gt\b"), ">"),
    (re.compile(r"\\times|\\cdot|\\ast"), "*"),
    (re.compile(r"\\left|\\right"), ""),
    (re.compile(r"\\,"), ""),
    (re.compile(r"\\;"), ""),
    (re.compile(r"\\ "), " "),
]

_REL_OPS = (
    ("<=", Le),
    (">=", Ge),
    ("!=", Ne),
    ("=", Eq),
    ("<", Lt),
    (">", Gt),
)


def normalize_math_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("&", " ")
    cleaned = "\n".join(
        line for line in cleaned.splitlines() if not line.strip().startswith("%")
    )
    cleaned = " ".join(cleaned.split())
    cleaned = _FINAL_ANSWER_PREFIX_RE.sub("", cleaned).strip()
    for pattern, repl in _LATEX_REPLACEMENTS:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = cleaned.replace(r"\{", "(").replace(r"\}", ")")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    # Drop remaining simple latex commands like \begin{aligned}
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned


def parse_relation(text: str, symbol: Symbol | None = None) -> Relational:
    """Parse an equation or inequality into a SymPy Relational."""
    normalized = normalize_math_text(text)
    if not normalized:
        raise MathParseError(text, "empty expression")

    local_dict: dict[str, object] = {}
    if symbol is not None:
        local_dict[str(symbol)] = symbol

    candidates = [normalized]
    # Prefer the last clause that looks like a relation (handles prose prefixes).
    for part in re.split(r"[;\n]", text):
        part_norm = normalize_math_text(part)
        if part_norm and part_norm not in candidates:
            candidates.append(part_norm)

    errors: list[str] = []
    for candidate in candidates:
        try:
            return _parse_relation_candidate(candidate, local_dict)
        except MathParseError as exc:
            errors.append(str(exc.reason))

    raise MathParseError(text, errors[-1] if errors else "parse failed")


def _parse_relation_candidate(
    normalized: str,
    local_dict: dict[str, object],
) -> Relational:
    for op, constructor in _REL_OPS:
        if op not in normalized:
            continue
        left_raw, right_raw = normalized.split(op, 1)
        left_raw = left_raw.strip()
        right_raw = right_raw.strip()
        if not left_raw or not right_raw:
            continue
        # Skip if left still contains a longer relational opener mishandled
        if any(other in left_raw for other, _ in _REL_OPS if other != op):
            continue
        try:
            left = _parse_side(left_raw, local_dict)
            right = _parse_side(right_raw, local_dict)
            return constructor(left, right)
        except (SyntaxError, TypeError, ValueError, Exception) as exc:
            raise MathParseError(normalized, str(exc)) from exc

    raise MathParseError(normalized, "no supported relation operator found")


def _parse_side(side: str, local_dict: dict[str, object]) -> Expr:
    return parse_expr(
        side,
        local_dict=local_dict,
        transformations=_TRANSFORMATIONS,
        evaluate=False,
    )


def default_symbol() -> Symbol:
    return Symbol("x")
