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
# Closing ``>`` must not be the ``>`` inside ``>=`` (Piecewise / chained ineq).
_ASCII_ANGLE_RE = re.compile(
    r"<(?P<body>[^<>]*,[^<>]*)>(?!=)",
)

_LVERT_NORM_RE = re.compile(
    r"\\lVert\s*(?P<body>.+?)\s*\\rVert",
    re.DOTALL,
)

_LATEX_DOUBLE_BAR_NORM_RE = re.compile(r"\\\|\s*(?P<body>.+?)\s*\\\|", re.DOTALL)

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

# Named vectors: \mathbf{u}, \vec{u}, \overrightarrow{AB}, \boldsymbol{u}
_NAMED_VECTOR = r"\\(?:mathbf|vec|overrightarrow|boldsymbol)\s*\{\s*[^{}]+?\s*\}"
_NAMED_VECTOR_RE = re.compile(
    r"\\(?:mathbf|vec|overrightarrow|boldsymbol)\s*\{\s*(?P<name>[^{}]+?)\s*\}"
)
_CROSS_RE = re.compile(rf"({_NAMED_VECTOR})\s*\\times\s*({_NAMED_VECTOR})")
# ``\times`` is a cross product only between 3-component column literals;
# between other matrices it stays a product.
_COLUMN3 = r"MATRIX\(\[\[[^\[\]]*\],\[[^\[\]]*\],\[[^\[\]]*\]\]\)"
_LITERAL_CROSS_RE = re.compile(rf"({_COLUMN3})\s*\\times\s*({_COLUMN3})")
_CROSS_TOKEN = r"CROSS\([^()]*\)"
_NAMED_DOT_RE = re.compile(
    rf"({_NAMED_VECTOR}|{_CROSS_TOKEN})\s*\\cdot\s*"
    rf"({_NAMED_VECTOR}|\(\s*{_CROSS_TOKEN}\s*\)|{_CROSS_TOKEN})"
)
# ``\|\mathbf u\| = \sqrt{...}`` / ``\mathbf u \cdot \mathbf v = (1)(3) + ...``:
# named vectors are opaque, so the step is the scalar work on the right.
_OPAQUE_SCALAR_LHS_RE = re.compile(r"^\s*(?:NORM|DOT)\((?:[^()]|\([^()]*\))*\)\s*=\s*(?=\S)")

_TUPLE_SPACING_RE = re.compile(r"\\[,;:! ]")


def _angle_body_to_matrix_token(body: str) -> str:
    parts = [part.strip() for part in body.split(",") if part.strip() != ""]
    if not parts:
        return "MATRIX([])"
    cols = ",".join(f"[{part}]" for part in parts)
    return f"MATRIX([{cols}])"


def _vector_name(match: re.Match[str]) -> str:
    return re.sub(r"[^\w]", "", match.group("name"))


def _strip_parens(token: str) -> str:
    stripped = token.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return stripped[1:-1].strip()
    return stripped


def _rewrite_named_products(text: str) -> str:
    """``\\mathbf u \\times \\mathbf v`` → ``CROSS(u,v)``; ``\\mathbf u \\cdot (...)`` → ``DOT(u,...)``."""
    cleaned = _CROSS_RE.sub(r"CROSS(\1,\2)", text)
    cleaned = _NAMED_DOT_RE.sub(
        lambda m: f"DOT({m.group(1)},{_strip_parens(m.group(2))})", cleaned
    )
    return _NAMED_VECTOR_RE.sub(_vector_name, cleaned)


def rewrite_vector_notation(text: str) -> str:
    """Rewrite vector forms into MATRIX / NORM / DOT / CROSS tokens.

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

    cleaned = _LITERAL_CROSS_RE.sub(r"CROSS(\1,\2)", cleaned)
    cleaned = _DOT_RE.sub(r"DOT(\1,\2)", cleaned)
    cleaned = _rewrite_named_products(cleaned)

    cleaned = _LVERT_NORM_RE.sub(r"NORM(\1)", cleaned)
    cleaned = _LATEX_DOUBLE_BAR_NORM_RE.sub(r"NORM(\1)", cleaned)
    cleaned = _DOUBLE_BAR_NORM_RE.sub(r"NORM(\1)", cleaned)

    lhs = _OPAQUE_SCALAR_LHS_RE.match(cleaned)
    if lhs is not None and "MATRIX(" not in lhs.group(0):
        cleaned = cleaned[lhs.end():]

    assign = _ASSIGN_PREFIX_RE.match(cleaned)
    if assign is not None:
        rhs = assign.group("rhs").strip()
        if any(tok in rhs for tok in ("NORM(", "DOT(", "MATRIX(")):
            cleaned = rhs

    return cleaned


def _matching_paren(text: str, start: int) -> int | None:
    """Index of the ``)`` closing ``text[start] == "("``; None for ``(a, b]`` / unbalanced."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char in "({":
            depth += 1
        elif char in ")}":
            depth -= 1
            if depth == 0:
                return index if char == ")" else None
        elif char == "]" and depth == 1:
            return None
    return None


def _top_level_parts(body: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts]


def rewrite_vector_tuples(text: str) -> str:
    """``(a, b, c)`` component tuples → column ``MATRIX([[a],[b],[c]])`` (vector packs only).

    Not a call (``d(P, Q)``, ``f(x, y)``), not an interval after ``\\in`` and not
    half-open ``(a, b]``; the generic chain reads ``(a, b)`` as an interval.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "(":
            out.append(char)
            index += 1
            continue
        before = text[:index]
        is_call = bool(before) and (before[-1].isalnum() or before[-1] in "_}") and not before.endswith(
            "\\left"
        )
        close = _matching_paren(text, index)
        if is_call or close is None or re.search(r"\\in\s*(?:\\left\s*)?$", before):
            out.append(char)
            index += 1
            continue
        body = re.sub(r"\\right\s*$", "", text[index + 1 : close])
        parts = _top_level_parts(_TUPLE_SPACING_RE.sub(" ", body))
        if len(parts) < 2 or not all(parts):
            out.append(char)
            index += 1
            continue
        if before.endswith("\\left"):
            out[-len("\\left") :] = []
        rows = ",".join(f"[{rewrite_vector_tuples(part)}]" for part in parts)
        out.append(f"MATRIX([{rows}])")
        index = close + 1
    rewritten = _LITERAL_CROSS_RE.sub(r"CROSS(\1,\2)", "".join(out))
    return _DOT_RE.sub(r"DOT(\1,\2)", rewritten)
