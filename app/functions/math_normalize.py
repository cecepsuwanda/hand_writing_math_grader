"""Normalize LaTeX / mixed math strings into SymPy-friendly text (pure FP)."""

from __future__ import annotations

import re

from app.functions.abs_normalize import rewrite_abs_notation
from app.functions.derivative_normalize import rewrite_derivative_notation
from app.functions.det_inverse_normalize import rewrite_det_inverse_notation
from app.functions.frac_normalize import rewrite_frac_notation
from app.functions.integral_normalize import rewrite_integral_notation
from app.functions.interval_normalize import rewrite_interval_membership
from app.functions.limit_normalize import rewrite_limit_notation
from app.functions.matrix_normalize import rewrite_matrix_notation
from app.functions.transcendental_normalize import rewrite_transcendental_notation
from app.functions.vector_normalize import rewrite_vector_notation

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


def normalize_math_text(text: str) -> str:
    """Convert LaTeX-ish math into a SymPy-parseable string."""
    cleaned = text.strip()
    # Matrix rewrite before '&' → space (LaTeX column separators).
    cleaned = rewrite_matrix_notation(cleaned)
    cleaned = rewrite_det_inverse_notation(cleaned)
    cleaned = rewrite_vector_notation(cleaned)
    cleaned = cleaned.replace("&", " ")
    cleaned = "\n".join(
        line for line in cleaned.splitlines() if not line.strip().startswith("%")
    )
    cleaned = " ".join(cleaned.split())
    cleaned = _FINAL_ANSWER_PREFIX_RE.sub("", cleaned).strip()
    cleaned = rewrite_abs_notation(cleaned)
    # Strip before interval rewrite so \left(...\right] matches interval atoms.
    cleaned = re.sub(r"\\left|\\right", "", cleaned)
    cleaned = rewrite_interval_membership(cleaned)
    cleaned = rewrite_limit_notation(cleaned)
    cleaned = rewrite_derivative_notation(cleaned)
    cleaned = rewrite_integral_notation(cleaned)
    cleaned = rewrite_transcendental_notation(cleaned)
    for pattern, repl in _LATEX_REPLACEMENTS:
        cleaned = pattern.sub(repl, cleaned)
    # Expand \frac before brace flattening so {a}{b} does not become (a)(b).
    cleaned = rewrite_frac_notation(cleaned)
    cleaned = cleaned.replace(r"\{", "(").replace(r"\}", ")")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned
