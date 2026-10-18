"""Convert LaTeX math strings into SymbolicPayload (pure FP, no LLM)."""

from __future__ import annotations

import re

from app.functions.math_normalize import IMPLICATION_TOKEN, normalize_math_text
from app.functions.piecewise_normalize import (
    rewrite_piecewise_notation,
    rewrite_pseudo_if_piecewise,
)
from app.models.recognition import SymbolicKind, SymbolicPayload

_TEXT_ONLY_RE = re.compile(
    r"^\\text\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*$",
    re.IGNORECASE,
)

_DOLLAR_RE = re.compile(r"\$+")

_TOKEN_KINDS: list[tuple[re.Pattern[str], SymbolicKind]] = [
    (re.compile(r"^NUMBER_LINE\s*\(", re.IGNORECASE), "figure"),
    (re.compile(r"^GRAPH_POINTS\s*\(", re.IGNORECASE), "figure"),
    (re.compile(r"^LIMIT\(", re.IGNORECASE), "limit"),
    (re.compile(r"^DIFF\(", re.IGNORECASE), "derivative"),
    (re.compile(r"^INT\(", re.IGNORECASE), "integral"),
    (re.compile(r"^MATRIX\(", re.IGNORECASE), "matrix"),
]

# Relation ops that are not mere interval brackets (e.g. [-1, 6]).
_RELATION_OP_RE = re.compile(r"(<=|>=|!=|==|=|<|>)")

_IMPLICATION_MARKER_RE = re.compile(
    r"\\implies\b|\\Rightarrow\b|\\Longrightarrow\b|→|⇒|⟹|=>",
    re.IGNORECASE,
)

_NUMBER_LINE_PREFIX_RE = re.compile(r"^\s*NUMBER_LINE\s*\(", re.IGNORECASE)
_GRAPH_POINTS_PREFIX_RE = re.compile(r"^\s*GRAPH_POINTS\s*\(", re.IGNORECASE)
_GRAPH_POINTS_IN_TEXT_RE = re.compile(
    r"GRAPH_POINTS\s*\([^)]*\)",
    re.IGNORECASE | re.DOTALL,
)
_CASES_RE = re.compile(r"\\begin\s*\{\s*cases\s*\}", re.IGNORECASE)
_PSEUDO_IF_RE = re.compile(
    r"(\{[^{}]*\bif\b[^{}]*\})|(\bif\b.+\bif\b)",
    re.IGNORECASE | re.DOTALL,
)
_UNCERTAIN_META_RE = re.compile(
    r"\[\s*(?:uncertain|note|ocr)?\s*:?[^\]]*\]",
    re.IGNORECASE,
)
_NUMERIC_PAIR_RE = re.compile(
    r"\(\s*(?P<x>[-+]?\d[\d./]*)\s*,\s*(?P<y>[-+]?\d[\d./]*)\s*\)\s*$"
)
_FAKE_INTERVAL_RE = re.compile(
    r"[-+]?\d[\d./]*\s*<\s*x\s*<\s*[-+]?\d[\d./]*\s*$",
    re.IGNORECASE,
)
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
        "piecewise",
    }
)

_WORD_RE = re.compile(r"[A-Za-z]+")
_PROSE_WORD_RE = re.compile(r"(?<!\\)\b[A-Za-z]{4,}\b")


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
    normalized = normalize_math_text(stripped, keep_implication=True)
    if not normalized:
        return None
    # After normalize, pure narrative leftovers (no math tokens) are useless.
    if (
        re.fullmatch(r"[A-Za-z\s,:;.]+", normalized)
        and not re.search(r"[\d=<>]", normalized)
        and normalized.strip() != "oo"
    ):
        return None
    return SymbolicPayload(kind=infer_symbolic_kind(normalized), repr=normalized)


def _strip_uncertain_meta(text: str) -> str:
    """Drop ``[uncertain: …]`` / OCR asides so they never enter symbolic.repr."""
    cleaned = _UNCERTAIN_META_RE.sub(" ", text or "")
    return " ".join(cleaned.split())


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
        start = match.start()
        if start > 0 and match.string[start - 1] == "\\":
            return token
        if token.lower() in _MATH_WORDS:
            return token
        if len(token) >= 3 and token.isalpha():
            return " "
        return token

    cleaned = _WORD_RE.sub(word, cleaned)
    return " ".join(cleaned.split())


def _usable_math(text: str) -> bool:
    """True when ``text`` has a relation/number and no leftover prose words."""
    if not text:
        return False
    if _NUMERIC_PAIR_RE.search(text.strip()):
        return True
    if "Piecewise(" in text:
        return True
    if not re.search(r"[\d=<>]", text):
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


def _looks_like_graph_points(text: str) -> bool:
    return bool(_GRAPH_POINTS_PREFIX_RE.match((text or "").strip()))


def _has_latex_tokens(text: str) -> bool:
    return bool(_LATEX_TOKEN_RE.search(text or ""))


def _needs_piecewise_rebuild(raw: str, repr_text: str) -> bool:
    if _CASES_RE.search(raw or ""):
        return True
    blob = f"{raw or ''}\n{repr_text or ''}"
    if _PSEUDO_IF_RE.search(blob) and "Piecewise(" not in (repr_text or ""):
        return True
    return False


def _trailing_point_from_raw(raw: str) -> str | None:
    """Last ``(a, b)`` numeric pair in raw (evaluation conclusion), if any."""
    matches = list(
        re.finditer(
            r"\(\s*[-+]?\d[\d./]*\s*,\s*[-+]?\d[\d./]*\s*\)",
            raw or "",
        )
    )
    if not matches:
        return None
    return matches[-1].group(0)


def _fix_fake_interval_conclusion(
    payload: SymbolicPayload,
    raw: str,
) -> SymbolicPayload:
    """If LLM turned ``→ (2,4)`` into ``=> 2 < x < 4``, restore the pair."""
    repr_text = (payload.repr or "").strip()
    if not repr_text or IMPLICATION_TOKEN not in repr_text:
        # Also handle single-clause fake interval.
        point = _trailing_point_from_raw(raw)
        if point and _FAKE_INTERVAL_RE.search(repr_text):
            return SymbolicPayload(kind="expression", repr=point)
        return payload

    head, _, tail = repr_text.rpartition(IMPLICATION_TOKEN)
    tail = tail.strip()
    if not _FAKE_INTERVAL_RE.search(tail):
        return payload
    point = _trailing_point_from_raw(raw)
    if point is None:
        return payload
    if head.strip():
        return SymbolicPayload(
            kind="relation",
            repr=f"{head.strip()}{IMPLICATION_TOKEN}{point}",
        )
    return SymbolicPayload(kind="expression", repr=point)


def _accept_rebuilt(payload: SymbolicPayload | None) -> SymbolicPayload | None:
    if payload is None:
        return None
    repr_text = (payload.repr or "").strip()
    if not repr_text:
        return None
    if _looks_like_number_line(repr_text) or _looks_like_graph_points(repr_text):
        return SymbolicPayload(kind="figure", repr=repr_text)
    if _usable_math(repr_text):
        return payload
    return None


def _rebuild_from_text(text: str) -> SymbolicPayload | None:
    """Best-effort SymbolicPayload from transcription / LaTeX-ish text."""
    source = _strip_uncertain_meta((text or "").strip())
    if not source:
        return None
    if _looks_like_number_line(source) or _looks_like_graph_points(source):
        return SymbolicPayload(kind="figure", repr=source)
    gp = _GRAPH_POINTS_IN_TEXT_RE.search(source)
    if gp is not None:
        return SymbolicPayload(kind="figure", repr=gp.group(0))

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
    ``symbolic.repr``, invents ``{… if …}`` for cases, or turns ``(2,4)`` into
    ``2 < x < 4``. Prefer a deterministic rebuild from ``raw_text``.
    """
    raw = _strip_uncertain_meta((raw_text or "").strip())
    repr_text = ((symbolic.repr if symbolic is not None else "") or "").strip()
    repr_text = _strip_uncertain_meta(repr_text)

    # Figure step with empty repr but GRAPH_POINTS in caption / raw.
    if symbolic is not None and symbolic.kind == "figure":
        if _looks_like_graph_points(repr_text) or _looks_like_number_line(repr_text):
            return SymbolicPayload(kind="figure", repr=repr_text)
        gp = _GRAPH_POINTS_IN_TEXT_RE.search(raw)
        if gp is not None:
            return SymbolicPayload(kind="figure", repr=gp.group(0))
        if not repr_text:
            return symbolic

    # Piecewise: always rebuild from raw cases / fix pseudo-if LLM forms.
    if _needs_piecewise_rebuild(raw, repr_text):
        source = raw or rewrite_pseudo_if_piecewise(repr_text)
        rebuilt = _rebuild_from_text(source)
        if rebuilt is not None:
            return rebuilt
        # Direct notation rewrite when normalize pack lacks piecewise.
        rewritten = rewrite_piecewise_notation(source)
        if "Piecewise(" in rewritten:
            return SymbolicPayload(
                kind=infer_symbolic_kind(rewritten),
                repr=normalize_math_text(rewritten, keep_implication=True)
                or rewritten,
            )

    if raw and _IMPLICATION_MARKER_RE.search(raw):
        source = _implication_math_source(raw)
        rebuilt = latex_to_symbolic_payload(source) if source else None
        accepted = _accept_rebuilt(rebuilt)
        if accepted is not None:
            return _fix_fake_interval_conclusion(accepted, raw)

    if symbolic is None or not repr_text:
        rebuilt = _rebuild_from_text(raw)
        if rebuilt is not None:
            return rebuilt
        return symbolic

    if _looks_like_number_line(repr_text) or _looks_like_graph_points(repr_text):
        return SymbolicPayload(kind="figure", repr=repr_text)

    if _has_latex_tokens(repr_text):
        sanitized = _accept_rebuilt(latex_to_symbolic_payload(repr_text))
        if sanitized is not None:
            return _fix_fake_interval_conclusion(sanitized, raw)
        from_raw = _rebuild_from_text(raw)
        if from_raw is not None:
            return from_raw

    # LLM wrote a fake interval conclusion while raw has a point pair.
    if symbolic is not None:
        fixed = _fix_fake_interval_conclusion(
            SymbolicPayload(kind=symbolic.kind, repr=repr_text),
            raw,
        )
        if fixed.repr != repr_text:
            return fixed

    if (
        symbolic.kind == "expression"
        and repr_text
        and _RELATION_OP_RE.search(repr_text)
    ):
        return SymbolicPayload(
            kind=infer_symbolic_kind(repr_text),
            repr=repr_text,
        )
    return SymbolicPayload(kind=symbolic.kind, repr=repr_text) if symbolic else None
