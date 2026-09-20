"""Pure string transforms for vector notation before SymPy parse."""

from __future__ import annotations

import re

# Nested MATRIX(...) / TRANSPOSE(...) token (one level of inner parens)
_MATRIX_LIKE = r"(?:MATRIX|TRANSPOSE)\((?:[^()]|\([^()]*\))*\)"

_LATEX_ANGLE_RE = re.compile(
    r"\\langle\s*(?P<body>.*?)\s*\\rangle",
    re.IGNORECASE | re.DOTALL,
)

# Require at least one comma so inequalities like 1<x are not matched.
_ASCII_ANGLE_RE = re.compile(
    r"<(?P<body>[^<>]*,[^<>]*)>",
)

_LVERT_NORM_RE = re.compile(
    r"\\lVert\s*(?P<body>.+?)\s*\\rVert",
    re.DOTALL,
)

_DOUBLE_BAR_NORM_RE = re.compile(
    r"\|\|(?P<body>.+?)\|\|",
)

_DOT_RE = re.compile(
    rf"({_MATRIX_LIKE})\s*(?:\\cdot|·)\s*({_MATRIX_LIKE})",
    re.IGNORECASE,
)

_ASSIGN_PREFIX_RE = re.compile(
    r"^(?P<lhs>[A-Za-z]\w*)\s*=\s*(?P<rhs>.+)$",
    re.DOTALL,
)


def _angle_body_to_matrix_token(body: str) -> str:
    parts = [part.strip() for part in body.split(",") if part.strip() != ""]
    if not parts:
        return "MATRIX([])"
    cols = ",".join(f"[{part}]" for part in parts)
    return f"MATRIX([{cols}])"


def rewrite_vector_notation(text: str) -> str:
    """Rewrite vector forms into MATRIX / NORM / DOT tokens.

    Expects ``rewrite_matrix_notation`` (and det/inv) to have run first.
    Does not rewrite bare ``|...|`` (conflicts with Abs).
    Must run before ``\\cdot`` → ``*`` latex replacements.
    """
    cleaned = text.strip()

    cleaned = _LATEX_ANGLE_RE.sub(
        lambda match: _angle_body_to_matrix_token(match.group("body")),
        cleaned,
    )
    cleaned = _ASCII_ANGLE_RE.sub(
        lambda match: _angle_body_to_matrix_token(match.group("body")),
        cleaned,
    )

    cleaned = _DOT_RE.sub(r"DOT(\1,\2)", cleaned)

    cleaned = _LVERT_NORM_RE.sub(r"NORM(\1)", cleaned)
    cleaned = _DOUBLE_BAR_NORM_RE.sub(r"NORM(\1)", cleaned)

    assign = _ASSIGN_PREFIX_RE.match(cleaned)
    if assign is not None:
        rhs = assign.group("rhs").strip()
        if any(tok in rhs for tok in ("NORM(", "DOT(", "MATRIX(")):
            cleaned = rhs

    return cleaned
