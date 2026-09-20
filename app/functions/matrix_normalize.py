"""Pure string transforms for matrix notation before SymPy parse."""

from __future__ import annotations

import re

# LaTeX pmatrix / bmatrix environments
_LATEX_MATRIX_RE = re.compile(
    r"\\begin\s*\{\s*(?:p|b)matrix\s*\}(?P<body>.*?)\\end\s*\{\s*(?:p|b)matrix\s*\}",
    re.IGNORECASE | re.DOTALL,
)

# Optional assignment prefix: A = MATRIX(...)
_ASSIGN_PREFIX_RE = re.compile(
    r"^(?P<lhs>[A-Za-z]\w*)\s*=\s*(?P<rhs>.+)$",
    re.DOTALL,
)

# Transpose markers after a MATRIX(...) token (before brace stripping)
_TRANSPOSE_RE = re.compile(
    r"(MATRIX\((?:[^()]|\([^()]*\))*\))\s*(?:\^\s*\{\s*T\s*\}|\^T|\.T)",
    re.IGNORECASE,
)

# Ascii nested list: [[1,2],[3,4]]
_ASCII_MATRIX_RE = re.compile(
    r"\[(\[[^\]]+\](?:\s*,\s*\[[^\]]+\])*)\]",
)


def _row_cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.split("&") if cell.strip() != ""]


def _latex_body_to_matrix_token(body: str) -> str:
    cleaned = body.strip()
    cleaned = cleaned.replace("\n", " ")
    rows_raw = re.split(r"\\\\", cleaned)
    rows: list[str] = []
    for row in rows_raw:
        row = row.strip().rstrip("\\").strip()
        if not row:
            continue
        cells = _row_cells(row)
        if not cells:
            continue
        rows.append("[" + ",".join(cells) + "]")
    if not rows:
        return "MATRIX([])"
    return "MATRIX([" + ",".join(rows) + "])"


def rewrite_matrix_notation(text: str) -> str:
    """Rewrite LaTeX/ascii matrices into ``MATRIX([[...]])`` tokens.

    Also rewrites transpose ``^T`` / ``^{T}`` into ``TRANSPOSE(MATRIX(...))``.
    """
    cleaned = text.strip()
    cleaned = _LATEX_MATRIX_RE.sub(
        lambda match: _latex_body_to_matrix_token(match.group("body")),
        cleaned,
    )

    def _ascii_repl(match: re.Match[str]) -> str:
        start = match.start()
        # Already wrapped: MATRIX([[...]])
        if start >= 7 and cleaned[start - 7 : start] == "MATRIX(":
            return match.group(0)
        return f"MATRIX({match.group(0)})"

    cleaned = _ASCII_MATRIX_RE.sub(_ascii_repl, cleaned)
    cleaned = _TRANSPOSE_RE.sub(r"TRANSPOSE(\1)", cleaned)

    # Implicit multiplication: 2MATRIX → 2*MATRIX, MATRIX(...)MATRIX → * between
    cleaned = re.sub(r"(\d)\s*(MATRIX\(|TRANSPOSE\()", r"\1*\2", cleaned)
    cleaned = re.sub(r"(\))\s*(MATRIX\(|TRANSPOSE\()", r"\1*\2", cleaned)

    assign = _ASSIGN_PREFIX_RE.match(cleaned)
    if assign is not None:
        rhs = assign.group("rhs").strip()
        if "MATRIX(" in rhs or "TRANSPOSE(" in rhs:
            cleaned = rhs

    return cleaned
