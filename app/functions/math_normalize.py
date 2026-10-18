"""Normalize LaTeX / mixed math strings into SymPy-friendly text (pure FP)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.capabilities.registry import ALL_CAPABILITY_IDS, apply_capabilities
from app.functions.frac_normalize import rewrite_frac_notation, rewrite_sqrt_notation
from app.functions.interval_normalize import rewrite_set_builder
from app.functions.piecewise_normalize import (
    restore_piecewise_tokens,
    stash_piecewise_tokens,
)
from app.functions.transcendental_normalize import rewrite_trig_application
from app.topics.runtime import get_active_pack

_FINAL_ANSWER_PREFIX_RE = re.compile(
    r"^(?:jawaban\s+akhir|final\s+answer|langkah)\s*[:：-]?\s*",
    re.IGNORECASE,
)

IMPLICATION_TOKEN = " => "

# Equivalence markers first so ``<=>`` is not read as ``<`` + ``=>``.
_IMPLICATION_RE = re.compile(
    r"<=>|⇔|⟺|\\iff\b|\\Leftrightarrow\b|\\Longleftrightarrow\b"
    r"|\\implies\b|\\Rightarrow\b|\\Longrightarrow\b|⇒|⟹|=>"
)

_LATEX_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\\text\s*\{([^{}]*)\}"), r" \1 "),
    (re.compile(r"\\q?quad(?![A-Za-z])"), " "),
    (re.compile(r"≤|⩽"), "<="),
    (re.compile(r"≥|⩾"), ">="),
    (re.compile(r"≠"), "!="),
    (re.compile(r"∞"), "oo"),
    (re.compile(r"[−–]"), "-"),
    (re.compile(r"[×·]"), "*"),
    (re.compile(r"\batau\b", re.IGNORECASE), " or "),
    (re.compile(r"\bdan\b", re.IGNORECASE), " and "),
    (re.compile(r"\\(?:leqslant|leq|le)(?![A-Za-z])"), "<="),
    (re.compile(r"\\(?:geqslant|geq|ge)(?![A-Za-z])"), ">="),
    (re.compile(r"\\(?:neq|ne)(?![A-Za-z])"), "!="),
    (re.compile(r"\\lt\b"), "<"),
    (re.compile(r"\\gt\b"), ">"),
    (re.compile(r"\\times|\\cdot|\\ast"), "*"),
    (re.compile(r"\\vee|\\lor\b"), " or "),
    (re.compile(r"\\wedge|\\land\b"), " and "),
    (re.compile(r"\\cup|\\bigcup\b"), " or "),
    (re.compile(r"\\cap|\\bigcap\b"), " and "),
    (re.compile(r"∪"), " or "),
    (re.compile(r"∩"), " and "),
    (re.compile(r"\\circ"), " o "),
    (re.compile(r"\\infty\b"), "oo"),
    (re.compile(r"\\to\b"), "->"),
    (re.compile(r"\\sin\b"), "sin"),
    (re.compile(r"\\cos\b"), "cos"),
    (re.compile(r"\\tan\b"), "tan"),
    (re.compile(r"\\sec\b"), "sec"),
    (re.compile(r"\\csc\b"), "csc"),
    (re.compile(r"\\cot\b"), "cot"),
    (re.compile(r"\\ln\b"), "ln"),
    (re.compile(r"\\log\b"), "log"),
    (re.compile(r"\\exp\b"), "exp"),
    (re.compile(r"\\prime\b"), "'"),
    (re.compile(r"\\left|\\right"), ""),
    (re.compile(r"\\,"), ""),
    (re.compile(r"\\;"), ""),
    (re.compile(r"\\ "), " "),
]


def _resolve_capability_ids(
    capability_ids: Sequence[str] | None,
) -> tuple[str, ...]:
    if capability_ids is not None:
        return tuple(capability_ids)
    pack = get_active_pack()
    if pack is not None:
        return tuple(pack.capability_ids)
    return ALL_CAPABILITY_IDS


# ``2x\sin x`` must not become the symbol ``xsin``.
_GLUED_FUNCTION_RE = re.compile(
    r"(?<=[A-Za-z0-9)}])(?=\\(?:sin|cos|tan|sec|csc|cot|ln|log|exp|sqrt)(?![A-Za-z]))"
)
# ``\ln|u|`` must not become the command ``\lnAbs`` once the bars are rewritten.
_FUNCTION_BEFORE_BAR_RE = re.compile(
    r"(\\(?:sin|cos|tan|sec|csc|cot|ln|log|exp))\s*(?=\||\\left\s*\||\\[bB]igg?l\s*\|)"
)
# ``= \frac{1}{3}\ln 33 \approx 1{,}1655``: a rounded value is not an equality claim.
_APPROX_TAIL_RE = re.compile(r"\s*(?:\\approx(?![A-Za-z])|≈)[^=<>]*")
_BRACED_DECIMAL_COMMA_RE = re.compile(r"(\d)\s*\{,\}\s*(\d)")
_OPENERS = "([{"
_CLOSERS = ")]}"


def rewrite_decimal_commas(text: str) -> str:
    """``0{,}5`` / ``0,5`` → ``0.5``; a comma inside brackets stays (``(0,5)`` is an interval)."""
    text = _BRACED_DECIMAL_COMMA_RE.sub(r"\1.\2", text)
    chars = list(text)
    depth = 0
    for index, char in enumerate(chars):
        if char in _OPENERS:
            depth += 1
        elif char in _CLOSERS:
            depth = max(0, depth - 1)
        elif (
            char == ","
            and depth == 0
            and 0 < index < len(chars) - 1
            and chars[index - 1].isdigit()
            and chars[index + 1].isdigit()
        ):
            chars[index] = "."
    return "".join(chars)


def split_implication_clauses(text: str) -> list[str]:
    """``A => B => C`` (any implication / iff marker) → ``[A, B, C]``; empty clauses dropped."""
    return [part.strip() for part in _IMPLICATION_RE.split(text or "") if part.strip()]


def normalize_math_text(
    text: str,
    *,
    capability_ids: Sequence[str] | None = None,
    keep_implication: bool = False,
) -> str:
    """Convert LaTeX-ish math into a SymPy-parseable string.

    Domain rewrites are driven by ``capability_ids`` (explicit), else the
    active TopicPack, else the full legacy capability chain.

    Implications become ``" => "`` with ``keep_implication`` (stored symbolic,
    split per clause by the validator); otherwise ``" and "`` so a single
    SymPy proposition can still be parsed.
    """
    if keep_implication:
        clauses = split_implication_clauses(text)
        if len(clauses) > 1:
            return IMPLICATION_TOKEN.join(
                normalize_math_text(clause, capability_ids=capability_ids)
                for clause in clauses
            )
    else:
        text = _IMPLICATION_RE.sub(" and ", text or "")
    cleaned = _GLUED_FUNCTION_RE.sub(" ", rewrite_decimal_commas(text.strip()))
    cleaned = _FUNCTION_BEFORE_BAR_RE.sub(r"\1 ", _APPROX_TAIL_RE.sub("", cleaned))
    caps = _resolve_capability_ids(capability_ids)

    # Piecewise cases before brace/`&` stripping; stash before matrix/vector
    # so ASCII ``<a,b>`` / brace rewrites cannot eat ``Piecewise`` bodies.
    early_ids = ("piecewise", "matrix", "det_inverse", "vector", "vector_tuple")
    early = [c for c in early_ids if c in caps]
    rest = [c for c in caps if c not in early_ids]
    piecewise_early = [c for c in early if c == "piecewise"]
    other_early = [c for c in early if c != "piecewise"]
    cleaned = apply_capabilities(cleaned, piecewise_early)
    cleaned, piecewise_slots = stash_piecewise_tokens(cleaned)
    cleaned = apply_capabilities(cleaned, other_early)
    cleaned = cleaned.replace("&", " ")
    cleaned = "\n".join(
        line for line in cleaned.splitlines() if not line.strip().startswith("%")
    )
    cleaned = " ".join(cleaned.split())
    cleaned = _FINAL_ANSWER_PREFIX_RE.sub("", cleaned).strip()

    # Abs before stripping \\left/\\right so bar forms stay intact; interval
    # needs \\left stripped first (legacy order).
    if "interval" in rest:
        cleaned = rewrite_set_builder(cleaned)
    if "abs" in rest:
        cleaned = apply_capabilities(cleaned, ("abs",))
        rest = [c for c in rest if c != "abs"]

    cleaned = re.sub(r"\\left|\\right", "", cleaned)
    cleaned = apply_capabilities(cleaned, rest)

    for pattern, repl in _LATEX_REPLACEMENTS:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = rewrite_sqrt_notation(rewrite_frac_notation(cleaned))
    cleaned = cleaned.replace(r"\{", "(").replace(r"\}", ")")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = rewrite_trig_application(" ".join(cleaned.split()))
    cleaned = restore_piecewise_tokens(cleaned, piecewise_slots)
    return cleaned
