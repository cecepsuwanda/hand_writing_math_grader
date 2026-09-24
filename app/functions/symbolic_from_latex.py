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
    (re.compile(r"^NUMBER_LINE\s*\(", re.IGNORECASE), "figure"),
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

_NUMBER_LINE_PREFIX_RE = re.compile(r"^\s*NUMBER_LINE\s*\(", re.IGNORECASE)
_LATEX_TOKEN_RE = re.compile(r"\\[a-zA-Z]+")

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


def _looks_like_number_line(text: str) -> bool:
    return bool(_NUMBER_LINE_PREFIX_RE.match((text or "").strip()))


def _has_latex_tokens(text: str) -> bool:
    return bool(_LATEX_TOKEN_RE.search(text or ""))


def _accept_rebuilt(payload: SymbolicPayload | None) -> SymbolicPayload | None:
    if payload is None:
        return None
    repr_text = (payload.repr or "").strip()
    if not repr_text:
        return None
    if _looks_like_number_line(repr_text):
        return SymbolicPayload(kind="figure", repr=repr_text)
    if _usable_math(repr_text):
        return payload
    return None


def _rebuild_from_text(text: str) -> SymbolicPayload | None:
    """Best-effort SymbolicPayload from transcription / LaTeX-ish text."""
    source = (text or "").strip()
    if not source:
        return None
    if _looks_like_number_line(source):
        return SymbolicPayload(kind="figure", repr=source)

    accepted = _accept_rebuilt(latex_to_symbolic_payload(source))
    if accepted is not None:
        return accepted

    stripped = _strip_prose(source)
    if stripped and stripped != source:
        return _accept_rebuilt(latex_to_symbolic_payload(stripped))
    return None


def coalesce_step_symbolic(
    raw_text: str,
    symbolic: SymbolicPayload | None,
) -> SymbolicPayload | None:
    """Rebuild or repair symbolic when implication / kind / LaTeX is inconsistent.

    Vision sometimes truncates ``A \\\\implies B`` to only ``A`` in
    ``symbolic.repr``, omits symbolic entirely, or leaves LaTeX in ``repr``.
    Prefer a deterministic rebuild from ``raw_text`` / normalized ``repr``.
    Prose-laden rebuilds are discarded.
    """
    raw = (raw_text or "").strip()
    if raw and _IMPLICATION_MARKER_RE.search(raw):
        source = _implication_math_source(raw)
        rebuilt = latex_to_symbolic_payload(source) if source else None
        accepted = _accept_rebuilt(rebuilt)
        if accepted is not None:
            return accepted

    repr_text = ((symbolic.repr if symbolic is not None else "") or "").strip()

    if symbolic is None or not repr_text:
        rebuilt = _rebuild_from_text(raw)
        if rebuilt is not None:
            return rebuilt
        return symbolic

    if _looks_like_number_line(repr_text):
        return SymbolicPayload(kind="figure", repr=repr_text)

    if _has_latex_tokens(repr_text):
        sanitized = _accept_rebuilt(latex_to_symbolic_payload(repr_text))
        if sanitized is not None:
            return sanitized
        from_raw = _rebuild_from_text(raw)
        if from_raw is not None:
            return from_raw

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
