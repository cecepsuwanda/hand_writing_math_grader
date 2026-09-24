"""Pure helpers: derive / parse / compare number-line geometry from HP."""

from __future__ import annotations

import re

from sympy import EmptySet, Interval, Union, oo, parse_expr
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    standard_transformations,
)

from app.functions.interval_normalize import rewrite_interval_membership
from app.models.exam_schema import (
    NumberLineEndpoint,
    NumberLineInterval,
    NumberLineSpec,
)
from app.models.recognition import SymbolicPayload
from app.models.validation import ValidationStatus

_NUMBER_LINE_RE = re.compile(
    r"^\s*NUMBER_LINE\s*\((.*)\)\s*$",
    re.IGNORECASE | re.DOTALL,
)

_INTERVAL_ATOM = r"[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[\])]"
_INTERVAL_FIND_RE = re.compile(_INTERVAL_ATOM)
_INTERVAL_PIECE_RE = re.compile(
    rf"(?P<left>[\[(])\s*(?P<a>[^,]+?)\s*,\s*(?P<b>[^)\]]+?)\s*(?P<right>[\])])"
)

_UNION_U_RE = re.compile(r"\)\s*U\s*\(", re.IGNORECASE)
_OR_SPLIT_RE = re.compile(r"\s+or\s+", re.IGNORECASE)
# Gap between two interval atoms: union marker, or whitespace (juxtaposition).
_INTERVAL_GAP_RE = re.compile(
    r"\s*(?:U|or|\\cup|∪)?\s*",
    re.IGNORECASE,
)
_ASCENDING_OPS = frozenset({"<", "<="})
_DESCENDING_OPS = frozenset({">", ">="})

# a op x op b  (chained)
_CHAIN_RE = re.compile(
    r"^(?P<a>.+?)\s*(?P<lop><=|>=|<|>)\s*"
    r"(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*"
    r"(?P<rop><=|>=|<|>)\s*(?P<b>.+)$"
)
# x op b
_VAR_LEFT_RE = re.compile(
    r"^(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?P<op><=|>=|<|>)\s*(?P<b>.+)$"
)
# a op x
_VAR_RIGHT_RE = re.compile(
    r"^(?P<a>.+?)\s*(?P<op><=|>=|<|>)\s*(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)$"
)

_OO_ALIASES = {
    "oo": oo,
    "+oo": oo,
    "inf": oo,
    "+inf": oo,
    "infty": oo,
    "-oo": -oo,
    "-inf": -oo,
    "-infty": -oo,
}

_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)


def number_line_from_symbolic(
    payload: SymbolicPayload | str | None,
) -> NumberLineSpec | None:
    """Build ``NumberLineSpec`` from HP symbolic payload or raw text."""
    if payload is None:
        return None
    if isinstance(payload, SymbolicPayload):
        text = (payload.repr or "").strip()
    else:
        text = (payload or "").strip()
    if not text:
        return None
    return parse_number_line_repr(text)


def number_line_to_repr(spec: NumberLineSpec) -> str:
    """Canonical ASCII: ``NUMBER_LINE([-10/3,oo))`` / unions with ``U``."""
    if not spec.intervals:
        return "NUMBER_LINE()"
    parts = [_interval_to_ascii(iv) for iv in spec.intervals]
    return f"NUMBER_LINE({'U'.join(parts)})"


def parse_number_line_repr(text: str) -> NumberLineSpec | None:
    """Parse ``NUMBER_LINE(...)``, bare intervals, or inequality HP forms."""
    return _parse_number_line(text, allow_inequalities=True)


def parse_number_line_intervals_only(text: str) -> NumberLineSpec | None:
    """Parse ``NUMBER_LINE(...)`` / bare interval atoms; reject inequalities."""
    return _parse_number_line(text, allow_inequalities=False)


def _parse_number_line(
    text: str,
    *,
    allow_inequalities: bool,
) -> NumberLineSpec | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    wrapped = _NUMBER_LINE_RE.match(cleaned)
    if wrapped is not None:
        cleaned = wrapped.group(1).strip()
        if not cleaned:
            return NumberLineSpec(intervals=[])

    cleaned = _UNION_U_RE.sub(r")\\cup(", cleaned)
    cleaned = cleaned.replace("∪", r"\cup")

    from_intervals = _from_interval_atoms(cleaned)
    if from_intervals is not None:
        return from_intervals

    rewritten = rewrite_interval_membership(cleaned)
    from_intervals = _from_interval_atoms(rewritten)
    if from_intervals is not None:
        return from_intervals

    if not allow_inequalities:
        return None
    return _from_inequality_text(rewritten)


def compare_number_lines(
    expected: NumberLineSpec,
    actual: NumberLineSpec,
) -> tuple[ValidationStatus, str]:
    """SymPy set-equivalence of shaded regions (open/closed included)."""
    try:
        left = _spec_to_set(expected)
        right = _spec_to_set(actual)
    except Exception as exc:  # noqa: BLE001 — parse failures → uncertain
        return (
            ValidationStatus.UNCERTAIN,
            f"could not compare number lines: {exc}",
        )
    try:
        if left == right:
            return ValidationStatus.VALID, "number line matches HP geometry"
        return ValidationStatus.INVALID, "number line does not match HP geometry"
    except Exception as exc:  # noqa: BLE001
        return (
            ValidationStatus.UNCERTAIN,
            f"could not compare number lines: {exc}",
        )


def _interval_to_ascii(iv: NumberLineInterval) -> str:
    left_br = "[" if iv.left is not None and iv.left.closed else "("
    right_br = "]" if iv.right is not None and iv.right.closed else ")"
    a = iv.left.value if iv.left is not None else "-oo"
    b = iv.right.value if iv.right is not None else "oo"
    return f"{left_br}{a},{b}{right_br}"


def _from_interval_atoms(text: str) -> NumberLineSpec | None:
    matches = list(_INTERVAL_FIND_RE.finditer(text))
    if not matches:
        return None
    # Embedded "(a, b)" inside prose is not a number line.
    if not _interval_matches_cover(text, matches):
        return None
    intervals: list[NumberLineInterval] = []
    for match in matches:
        parsed = _parse_interval_atom(match.group(0))
        if parsed is None:
            return None
        intervals.append(parsed)
    return NumberLineSpec(intervals=intervals)


def _interval_matches_cover(text: str, matches: list[re.Match[str]]) -> bool:
    """True when atoms and union separators consume the whole string."""
    cursor = 0
    for index, match in enumerate(matches):
        gap = text[cursor : match.start()]
        if index == 0:
            if gap.strip():
                return False
        elif _INTERVAL_GAP_RE.fullmatch(gap) is None:
            return False
        cursor = match.end()
    return not text[cursor:].strip()


def _parse_interval_atom(atom: str) -> NumberLineInterval | None:
    match = _INTERVAL_PIECE_RE.fullmatch(atom.strip())
    if match is None:
        return None
    a = _normalize_bound_token(match.group("a"))
    b = _normalize_bound_token(match.group("b"))
    left_br = match.group("left")
    right_br = match.group("right")
    left = _endpoint_or_none(a, closed=(left_br == "["), is_left=True)
    right = _endpoint_or_none(b, closed=(right_br == "]"), is_left=False)
    return NumberLineInterval(left=left, right=right)


def _endpoint_or_none(
    token: str,
    *,
    closed: bool,
    is_left: bool,
) -> NumberLineEndpoint | None:
    key = token.strip().lower().replace("\\", "")
    if is_left and key in {"-oo", "-inf", "-infty"}:
        return None
    if not is_left and key in {"oo", "+oo", "inf", "+inf", "infty"}:
        return None
    if is_left and key in {"oo", "+oo", "inf", "infty"}:
        return None
    if not is_left and key in {"-oo", "-inf", "-infty"}:
        return None
    return NumberLineEndpoint(value=_canonical_bound_str(token), closed=closed)


def _normalize_bound_token(raw: str) -> str:
    text = raw.strip()
    text = text.replace(r"\infty", "oo").replace("∞", "oo")
    return " ".join(text.split())


def _canonical_bound_str(raw: str) -> str:
    token = _normalize_bound_token(raw)
    key = token.lower().replace("\\", "").replace("+", "")
    if key in {"oo", "inf", "infty"}:
        return "oo"
    if key in {"-oo", "-inf", "-infty"}:
        return "-oo"
    compact = re.sub(r"\s+", "", token)
    # -((10)/(3)) or -((10)/(3)) from normalize_math_text
    nested = re.fullmatch(r"(-?)\(\(+(-?\d+)\)/\(+(-?\d+)\)\)+", compact)
    if nested is not None:
        return f"{nested.group(1)}{nested.group(2)}/{nested.group(3)}"
    nested2 = re.fullmatch(r"(-?)\((-?\d+)/(-?\d+)\)", compact)
    if nested2 is not None:
        return f"{nested2.group(1)}{nested2.group(2)}/{nested2.group(3)}"
    return compact


def _from_inequality_text(text: str) -> NumberLineSpec | None:
    clauses = [c.strip() for c in _OR_SPLIT_RE.split(text) if c.strip()]
    if not clauses:
        return None
    intervals: list[NumberLineInterval] = []
    for clause in clauses:
        iv = _inequality_clause_to_interval(clause)
        if iv is None:
            return None
        intervals.append(iv)
    return NumberLineSpec(intervals=intervals)


def _flip_inequality_op(op: str) -> str:
    return {">": "<", ">=": "<=", "<": ">", "<=": ">="}[op]


def _inequality_clause_to_interval(clause: str) -> NumberLineInterval | None:
    cleaned = " ".join(clause.split())
    chain = _CHAIN_RE.match(cleaned)
    if chain is not None:
        a_raw = chain.group("a")
        b_raw = chain.group("b")
        lop = chain.group("lop")
        rop = chain.group("rop")
        ascending = lop in _ASCENDING_OPS and rop in _ASCENDING_OPS
        descending = lop in _DESCENDING_OPS and rop in _DESCENDING_OPS
        if not ascending and not descending:
            return None
        if descending:
            # ``b >= x > a`` is the same span as ``a < x <= b``.
            a_raw, b_raw = b_raw, a_raw
            lop, rop = _flip_inequality_op(rop), _flip_inequality_op(lop)
        a = _canonical_bound_str(a_raw)
        b = _canonical_bound_str(b_raw)
        left_closed = lop == "<="
        right_closed = rop == "<="
        return NumberLineInterval(
            left=_endpoint_or_none(a, closed=left_closed, is_left=True),
            right=_endpoint_or_none(b, closed=right_closed, is_left=False),
        )

    var_left = _VAR_LEFT_RE.match(cleaned)
    if var_left is not None:
        op = var_left.group("op")
        b = _canonical_bound_str(var_left.group("b"))
        if op == ">=":
            return NumberLineInterval(
                left=_endpoint_or_none(b, closed=True, is_left=True),
                right=None,
            )
        if op == ">":
            return NumberLineInterval(
                left=_endpoint_or_none(b, closed=False, is_left=True),
                right=None,
            )
        if op == "<=":
            return NumberLineInterval(
                left=None,
                right=_endpoint_or_none(b, closed=True, is_left=False),
            )
        if op == "<":
            return NumberLineInterval(
                left=None,
                right=_endpoint_or_none(b, closed=False, is_left=False),
            )

    var_right = _VAR_RIGHT_RE.match(cleaned)
    if var_right is not None:
        op = var_right.group("op")
        a = _canonical_bound_str(var_right.group("a"))
        if op == "<=":
            return NumberLineInterval(
                left=_endpoint_or_none(a, closed=True, is_left=True),
                right=None,
            )
        if op == "<":
            return NumberLineInterval(
                left=_endpoint_or_none(a, closed=False, is_left=True),
                right=None,
            )
        if op == ">=":
            return NumberLineInterval(
                left=None,
                right=_endpoint_or_none(a, closed=True, is_left=False),
            )
        if op == ">":
            return NumberLineInterval(
                left=None,
                right=_endpoint_or_none(a, closed=False, is_left=False),
            )
    return None


def _parse_bound(token: str):
    key = token.strip().lower().replace("\\", "")
    if key in _OO_ALIASES:
        return _OO_ALIASES[key]
    local = {"oo": oo}
    try:
        return parse_expr(
            token,
            local_dict=local,
            transformations=_TRANSFORMATIONS,
            evaluate=True,
        )
    except Exception:
        compact = re.sub(r"\s+", "", token)
        return parse_expr(
            compact,
            local_dict=local,
            transformations=_TRANSFORMATIONS,
            evaluate=True,
        )


def _spec_to_set(spec: NumberLineSpec):
    if not spec.intervals:
        return EmptySet
    pieces = []
    for iv in spec.intervals:
        left = -oo if iv.left is None else _parse_bound(iv.left.value)
        right = oo if iv.right is None else _parse_bound(iv.right.value)
        left_open = True if iv.left is None else not iv.left.closed
        right_open = True if iv.right is None else not iv.right.closed
        pieces.append(
            Interval(left, right, left_open=left_open, right_open=right_open)
        )
    if len(pieces) == 1:
        return pieces[0]
    return Union(*pieces)
