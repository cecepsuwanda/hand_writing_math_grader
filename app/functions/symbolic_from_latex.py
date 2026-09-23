"""Convert LaTeX math strings into SymbolicPayload (pure FP, no LLM)."""

from __future__ import annotations

import re

from app.functions.math_normalize import normalize_math_text
from app.models.recognition import SymbolicKind, SymbolicPayload

_TEXT_ONLY_RE = re.compile(
    r"^\\text\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*$",
    re.IGNORECASE,
)

_DOLLAR_RE = re.compile(r"\$+")

_TOKEN_KINDS: list[tuple[re.Pattern[str], SymbolicKind]] = [
    (re.compile(r"^LIMIT\(", re.IGNORECASE), "limit"),
    (re.compile(r"^DIFF\(", re.IGNORECASE), "derivative"),
    (re.compile(r"^INT\(", re.IGNORECASE), "integral"),
    (re.compile(r"^MATRIX\(", re.IGNORECASE), "matrix"),
]

# Relation ops that are not mere interval brackets (e.g. [-1, 6]).
_RELATION_OP_RE = re.compile(r"(<=|>=|!=|==|=|<|>)")


def infer_symbolic_kind(repr_text: str) -> SymbolicKind:
    """Infer SymbolicKind from a normalized math string."""
    stripped = repr_text.strip()
    for pattern, kind in _TOKEN_KINDS:
        if pattern.match(stripped):
            return kind
    if _RELATION_OP_RE.search(stripped):
        return "relation"
    return "expression"


def latex_to_symbolic_payload(latex: str) -> SymbolicPayload | None:
    """Normalize LaTeX to SymbolicPayload, or None if not usable math."""
    raw = (latex or "").strip()
    if not raw:
        return None
    if _TEXT_ONLY_RE.match(raw):
        return None
    # Strip outer $...$ / $$...$$ before normalize.
    stripped = _DOLLAR_RE.sub("", raw).strip()
    if not stripped or _TEXT_ONLY_RE.match(stripped):
        return None
    normalized = normalize_math_text(stripped)
    if not normalized:
        return None
    # After normalize, pure narrative leftovers (no math tokens) are useless.
    if re.fullmatch(r"[A-Za-z\s,:;.]+", normalized) and not re.search(
        r"[\d=<>]", normalized
    ):
        return None
    return SymbolicPayload(kind=infer_symbolic_kind(normalized), repr=normalized)
