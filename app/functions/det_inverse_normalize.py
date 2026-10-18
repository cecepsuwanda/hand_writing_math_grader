"""Pure string transforms for determinant / inverse notation before SymPy parse."""

from __future__ import annotations

import re

from app.functions.matrix_normalize import _latex_body_to_matrix_token

# Nested MATRIX(...) / TRANSPOSE(...) token (one level of inner parens)
_MATRIX_LIKE = r"(?:MATRIX|TRANSPOSE)\((?:[^()]|\([^()]*\))*\)"

_VMATRIX_RE = re.compile(
    r"\\begin\s*\{\s*vmatrix\s*\}(?P<body>.*?)\\end\s*\{\s*vmatrix\s*\}",
    re.IGNORECASE | re.DOTALL,
)

_INV_RE = re.compile(
    rf"({_MATRIX_LIKE})\s*"
    r"(?:\^\s*\{\s*-\s*1\s*\}|\^\s*\{\s*-1\s*\}|\^-1|\.inv)",
    re.IGNORECASE,
)

# \det MATRIX(...) / det(MATRIX(...)) / \det(MATRIX(...))
_DET_PREFIX_RE = re.compile(
    rf"(?:\\det|det)\s*"
    rf"(?:\(\s*({_MATRIX_LIKE})\s*\)|({_MATRIX_LIKE}))",
    re.IGNORECASE,
)

_ASSIGN_PREFIX_RE = re.compile(
    r"^(?P<lhs>[A-Za-z]\w*)\s*=\s*(?P<rhs>.+)$",
    re.DOTALL,
)

# \operatorname{tr}(A) / \mathrm{adj}(A) → TRACE(A) / ADJ(A); a bare literal
# operand (\operatorname{tr} MATRIX(...)) is wrapped: TRACE(MATRIX(...)).
_NAMED_OPERATOR_RE = re.compile(
    r"\\(?:operatorname|mathrm|text)\s*\{\s*(?P<name>tr|trace|adj)\s*\}\s*"
    rf"(?:(?=\()|(?P<operand>{_MATRIX_LIKE}))",
    re.IGNORECASE,
)
_NAMED_OPERATOR_TOKENS = {"tr": "TRACE", "trace": "TRACE", "adj": "ADJ"}

# ``\det(A) = <scalar work>`` / ``TRACE(4D^T - C) = 23 + 4 + 8``: a named (not
# literal) matrix is opaque, so the step is the scalar work on the right.
_OPAQUE_SCALAR_LHS_RE = re.compile(
    r"^\s*(?:\\det\s*\(\s*[A-Za-z]\w*\s*\)|TRACE\((?:[^()]|\([^()]*\))*\))\s*=\s*(?=\S)"
)
_DET_CALL_RE = re.compile(r"\\det\s*(?=\()")


def _named_operator_repl(match: re.Match[str]) -> str:
    token = _NAMED_OPERATOR_TOKENS[match.group("name").lower()]
    operand = match.group("operand")
    return f" {token}({operand})" if operand else f" {token}"


def rewrite_det_inverse_notation(text: str) -> str:
    """Rewrite det / inverse / trace / adjugate forms into ``DET`` / ``INV`` / ``TRACE`` / ``ADJ`` tokens.

    Expects ``rewrite_matrix_notation`` to have already produced ``MATRIX(...)``.
    Does not rewrite bare ``|...|`` (conflicts with Abs).
    """
    cleaned = text.strip()

    cleaned = _VMATRIX_RE.sub(
        lambda match: f"DET({_latex_body_to_matrix_token(match.group('body'))})",
        cleaned,
    )
    cleaned = _INV_RE.sub(r"INV(\1)", cleaned)

    def _det_repl(match: re.Match[str]) -> str:
        matrix_tok = match.group(1) or match.group(2)
        return f"DET({matrix_tok})"

    cleaned = _DET_PREFIX_RE.sub(_det_repl, cleaned)
    cleaned = _NAMED_OPERATOR_RE.sub(_named_operator_repl, cleaned)
    lhs = _OPAQUE_SCALAR_LHS_RE.match(cleaned)
    if lhs is not None and "MATRIX(" not in lhs.group(0):
        cleaned = cleaned[lhs.end():]
    cleaned = _DET_CALL_RE.sub(" DET", cleaned)

    assign = _ASSIGN_PREFIX_RE.match(cleaned)
    if assign is not None:
        rhs = assign.group("rhs").strip()
        if "DET(" in rhs or "INV(" in rhs:
            cleaned = rhs

    return cleaned
