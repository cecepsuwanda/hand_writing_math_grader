"""Pure string transforms for interval / membership notation."""

from __future__ import annotations

import re

# Single interval: (a,b) / [a,b] / (a,b] / [a,b)
_INTERVAL_ATOM = (
    r"[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[\])]"
)

_UNION_SEP = r"(?:\\cup|\\bigcup|∪)"
_INTERSECT_SEP = r"(?:\\cap|\\bigcap|∩)"

# x \in I1 \cup I2 \cup ...   (also \cap)
_IN_INTERVALS_RE = re.compile(
    rf"(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\\in|∈)\s*"
    rf"(?P<body>{_INTERVAL_ATOM}"
    rf"(?:\s*(?:{_UNION_SEP}|{_INTERSECT_SEP})\s*{_INTERVAL_ATOM})*)",
    re.IGNORECASE,
)

# Bare union/intersection of two or more intervals (no membership)
_BARE_INTERVALS_RE = re.compile(
    rf"(?P<body>{_INTERVAL_ATOM}"
    rf"(?:\s*(?:{_UNION_SEP}|{_INTERSECT_SEP})\s*{_INTERVAL_ATOM})+)",
    re.IGNORECASE,
)

# Entire string is a single interval answer, e.g. [-10/3, \infty)
_BARE_SINGLE_INTERVAL_RE = re.compile(
    rf"^\s*(?P<body>{_INTERVAL_ATOM})\s*$",
    re.IGNORECASE,
)

# HP = (a,b] / hp = [a,b) / H.P. = I1 \cup I2 ...
_HP_INTERVAL_RE = re.compile(
    rf"^\s*(?:H\.?P\.?|hp)\s*=\s*(?P<body>{_INTERVAL_ATOM}"
    rf"(?:\s*(?:{_UNION_SEP}|{_INTERSECT_SEP})\s*{_INTERVAL_ATOM})*)\s*$",
    re.IGNORECASE,
)

# HP(a,b) / HP[a,b) without '=' (recognition shorthand)
_HP_NO_EQ_INTERVAL_RE = re.compile(
    rf"^\s*(?:H\.?P\.?|hp)\s*(?P<body>{_INTERVAL_ATOM}"
    rf"(?:\s*(?:{_UNION_SEP}|{_INTERSECT_SEP})\s*{_INTERVAL_ATOM}"
    rf"|\s*{_INTERVAL_ATOM})*)\s*$",
    re.IGNORECASE,
)

# Entire string is juxtaposed intervals without ∪, e.g. (-∞,1)(1,∞)
_JUXTAPOSED_INTERVALS_RE = re.compile(
    rf"^\s*(?P<body>{_INTERVAL_ATOM}(?:\s*{_INTERVAL_ATOM})+)\s*$",
    re.IGNORECASE,
)

_INTERVAL_FIND_RE = re.compile(_INTERVAL_ATOM)

_INTERVAL_PIECE_RE = re.compile(
    rf"(?P<left>[\[(])\s*(?P<a>[^,]+?)\s*,\s*(?P<b>[^)\]]+?)\s*(?P<right>[\])])"
)

_SEP_SPLIT_RE = re.compile(
    rf"\s*(?:{_UNION_SEP}|{_INTERSECT_SEP})\s*",
    re.IGNORECASE,
)

_HAS_UNION_RE = re.compile(_UNION_SEP, re.IGNORECASE)
_HAS_INTERSECT_RE = re.compile(_INTERSECT_SEP, re.IGNORECASE)


def _interval_to_inequality(piece: str, var: str) -> str | None:
    match = _INTERVAL_PIECE_RE.fullmatch(piece.strip())
    if match is None:
        return None
    a = match.group("a").strip()
    b = match.group("b").strip()
    left = match.group("left")
    right = match.group("right")
    left_op = "<=" if left == "[" else "<"
    right_op = "<=" if right == "]" else "<"
    return f"{a} {left_op} {var} {right_op} {b}"


def _rewrite_interval_body(body: str, var: str) -> str | None:
    """Rewrite a chain of intervals joined by ∪/∩ (or juxtaposition) into inequalities."""
    pieces = [p.strip() for p in _SEP_SPLIT_RE.split(body) if p.strip()]
    if not pieces:
        return None

    # Single chunk may be juxtaposed atoms: (a,b)(c,d)
    if len(pieces) == 1:
        atoms = [m.group(0) for m in _INTERVAL_FIND_RE.finditer(pieces[0])]
        if len(atoms) >= 2:
            joined = " or ".join(
                ineq
                for piece in atoms
                if (ineq := _interval_to_inequality(piece, var)) is not None
            )
            if joined.count(" or ") + 1 == len(atoms):
                return joined
            return None

    inequalities: list[str] = []
    for piece in pieces:
        ineq = _interval_to_inequality(piece, var)
        if ineq is None:
            return None
        inequalities.append(ineq)

    if len(inequalities) == 1:
        return inequalities[0]

    # Mixed ∪ and ∩ in one chain is ambiguous; prefer ∪ → or, ∩ → and
    # when only one separator type appears.
    has_union = _HAS_UNION_RE.search(body) is not None
    has_intersect = _HAS_INTERSECT_RE.search(body) is not None
    if has_union and has_intersect:
        return None
    joiner = " or " if has_union or not has_intersect else " and "
    return joiner.join(inequalities)


def rewrite_interval_membership(text: str) -> str:
    """Rewrite ``x \\in (a,b)`` / unions / intersections / ``HP=`` into inequalities.

    Examples:
    - ``x \\in (1,3)`` → ``1 < x < 3``
    - ``x \\in (-\\infty,1) \\cup (1,\\infty)`` → ``-\\infty < x < 1 or 1 < x < \\infty``
    - ``(-\\infty,1) \\cup (1,\\infty)`` → same with free variable ``x``
    - ``HP = (-1/2, 2/3]`` → ``-1/2 < x <= 2/3``
    - ``HP = (-4, 0) \\cup (2, \\infty)`` → ``-4 < x < 0 or 2 < x < \\infty``
    - ``HP(1, oo)`` → ``1 < x < oo``
    - ``(-\\infty,1)(1,\\infty)`` → ``-\\infty < x < 1 or 1 < x < \\infty``
    """

    def _membership_repl(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        rewritten = _rewrite_interval_body(match.group("body"), var)
        return rewritten if rewritten is not None else match.group(0)

    cleaned = _IN_INTERVALS_RE.sub(_membership_repl, text)

    def _bare_repl(match: re.Match[str]) -> str:
        rewritten = _rewrite_interval_body(match.group("body"), "x")
        return rewritten if rewritten is not None else match.group(0)

    # HP= before bare union so ``HP = I1 ∪ I2`` is fully consumed (not left as ``HP = …``).
    hp_match = _HP_INTERVAL_RE.match(cleaned)
    if hp_match is not None:
        rewritten = _rewrite_interval_body(hp_match.group("body"), "x")
        if rewritten is not None:
            return rewritten

    hp_no_eq = _HP_NO_EQ_INTERVAL_RE.match(cleaned)
    if hp_no_eq is not None:
        rewritten = _rewrite_interval_body(hp_no_eq.group("body"), "x")
        if rewritten is not None:
            return rewritten

    cleaned = _BARE_INTERVALS_RE.sub(_bare_repl, cleaned)

    juxta = _JUXTAPOSED_INTERVALS_RE.match(cleaned)
    if juxta is not None:
        rewritten = _rewrite_interval_body(juxta.group("body"), "x")
        if rewritten is not None:
            return rewritten

    single = _BARE_SINGLE_INTERVAL_RE.match(cleaned)
    if single is not None:
        rewritten = _rewrite_interval_body(single.group("body"), "x")
        if rewritten is not None:
            cleaned = rewritten

    return cleaned
