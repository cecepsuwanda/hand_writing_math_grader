"""Normalize LaTeX / mixed math strings into SymPy-friendly text (pure FP)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.capabilities.registry import ALL_CAPABILITY_IDS, apply_capabilities
from app.functions.frac_normalize import rewrite_frac_notation
from app.topics.runtime import get_active_pack

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
    (re.compile(r"\\vee|\\lor\b"), " or "),
    (re.compile(r"\\wedge|\\land\b"), " and "),
    (re.compile(r"\\cup|\\bigcup\b"), " or "),
    (re.compile(r"\\cap|\\bigcap\b"), " and "),
    (re.compile(r"∪"), " or "),
    (re.compile(r"∩"), " and "),
    (re.compile(r"\\circ"), " o "),
    (re.compile(r"\\infty\b"), "oo"),
    (
        re.compile(
            r"\\implies\b|\\Rightarrow\b|\\Longrightarrow\b"
        ),
        " and ",
    ),
    (re.compile(r"⇒|⟹|=>"), " and "),
    (re.compile(r"\\to\b"), "->"),
    (re.compile(r"\\sin\b"), "sin"),
    (re.compile(r"\\cos\b"), "cos"),
    (re.compile(r"\\tan\b"), "tan"),
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


def normalize_math_text(
    text: str,
    *,
    capability_ids: Sequence[str] | None = None,
) -> str:
    """Convert LaTeX-ish math into a SymPy-parseable string.

    Domain rewrites are driven by ``capability_ids`` (explicit), else the
    active TopicPack, else the full legacy capability chain.
    """
    cleaned = text.strip()
    caps = _resolve_capability_ids(capability_ids)

    # Matrix / det / vector before '&' → space (LaTeX column separators).
    early = [c for c in ("matrix", "det_inverse", "vector") if c in caps]
    rest = [c for c in caps if c not in {"matrix", "det_inverse", "vector"}]
    cleaned = apply_capabilities(cleaned, early)
    cleaned = cleaned.replace("&", " ")
    cleaned = "\n".join(
        line for line in cleaned.splitlines() if not line.strip().startswith("%")
    )
    cleaned = " ".join(cleaned.split())
    cleaned = _FINAL_ANSWER_PREFIX_RE.sub("", cleaned).strip()

    # Abs before stripping \\left/\\right so bar forms stay intact; interval
    # needs \\left stripped first (legacy order).
    if "abs" in rest:
        cleaned = apply_capabilities(cleaned, ("abs",))
        rest = [c for c in rest if c != "abs"]

    cleaned = re.sub(r"\\left|\\right", "", cleaned)
    cleaned = apply_capabilities(cleaned, rest)

    for pattern, repl in _LATEX_REPLACEMENTS:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = rewrite_frac_notation(cleaned)
    cleaned = cleaned.replace(r"\{", "(").replace(r"\}", ")")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned
