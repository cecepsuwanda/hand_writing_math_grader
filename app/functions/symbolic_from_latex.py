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

_IMPLICATION_MARKER_RE = re.compile(
    r"\\implies\b|\\Rightarrow\b|\\Longrightarrow\b|⇒|⟹|=>",
    re.IGNORECASE,
)

# Words that are math, not Indonesian prose, when stripping narrative.
_MATH_WORDS = frozenset(
    {
        "sin",
        "cos",
        "tan",
        "log",
        "ln",
        "exp",
        "abs",
        "oo",
        "inf",
        "pi",
        "sqrt",
        "and",
        "or",
        "not",
    }
)

_WORD_RE = re.compile(r"[A-Za-z]+")
_PROSE_WORD_RE = re.compile(r"\b[A-Za-z]{4,}\b")


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


def _strip_prose(text: str) -> str:
    """Drop narrative words and prose parentheticals; keep math tokens."""

    def paren(match: re.Match[str]) -> str:
        inner = match.group(1)
        if re.search(r"[\d=<>\\]|[A-Za-z]\s*[\^+\-*/]", inner):
            return match.group(0)
        return " "

    cleaned = re.sub(r"\\text\s*\{([^{}]*)\}", " ", text)
    cleaned = re.sub(r"\(([^)]*)\)", paren, cleaned)

    def word(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.lower() in _MATH_WORDS:
            return token
        if len(token) >= 3 and token.isalpha():
            return " "
        return token

    cleaned = _WORD_RE.sub(word, cleaned)
    return " ".join(cleaned.split())


def _usable_math(text: str) -> bool:
    """True when ``text`` has a relation/number and no leftover prose words."""
    if not text or not re.search(r"[\d=<>]", text):
        return False
    for word in _PROSE_WORD_RE.findall(text):
        if word.lower() not in _MATH_WORDS:
            return False
    return True


def _implication_math_source(raw: str) -> str | None:
    """Math clauses around an implication, without surrounding prose."""
    clauses: list[str] = []
    for part in _IMPLICATION_MARKER_RE.split(raw):
        cleaned = _strip_prose(part)
        if _usable_math(cleaned):
            clauses.append(cleaned)
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return r" \implies ".join(clauses)


def coalesce_step_symbolic(
    raw_text: str,
    symbolic: SymbolicPayload | None,
) -> SymbolicPayload | None:
    """Rebuild or repair symbolic when implication / kind is inconsistent.

    Vision sometimes truncates ``A \\\\implies B`` to only ``A`` in
    ``symbolic.repr``. Prefer a deterministic rebuild from the math span
    of ``raw_text``. Prose-laden rebuilds are discarded.
    """
    raw = (raw_text or "").strip()
    if raw and _IMPLICATION_MARKER_RE.search(raw):
        source = _implication_math_source(raw)
        rebuilt = latex_to_symbolic_payload(source) if source else None
        if rebuilt is not None and _usable_math(rebuilt.repr):
            return rebuilt

    if symbolic is None:
        return None

    repr_text = (symbolic.repr or "").strip()
    if (
        symbolic.kind == "expression"
        and repr_text
        and _RELATION_OP_RE.search(repr_text)
    ):
        return SymbolicPayload(
            kind=infer_symbolic_kind(repr_text),
            repr=repr_text,
        )
    return symbolic
