"""Normalize and parse student math strings into SymPy propositions, expressions, or limits."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sympy import (
    Abs,
    And,
    E,
    Eq,
    Expr,
    Ge,
    Gt,
    Integer,
    Interval,
    Le,
    Lt,
    Matrix,
    Ne,
    Or,
    S,
    Symbol,
    cos,
    exp,
    log,
    oo,
    sin,
    tan,
)
from sympy.core.relational import Relational
from sympy.logic.boolalg import Boolean
from sympy.sets.sets import Set
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    rationalize,
    standard_transformations,
)

from app.exceptions import MathParseError
from app.functions.interval_normalize import EMPTY_SET_TOKEN, REALS_TOKEN
from app.functions.math_normalize import normalize_math_text

# ``rationalize``: SymPy 1.13+ treats Float(0.5) != Rational(1, 2), so decimals
# are made exact at parse time and compare equal to the matching fraction.
_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
    rationalize,
)

_OR_SPLIT_RE = re.compile(r"\s+(?:or|∨)\s+", re.IGNORECASE)
_AND_SPLIT_RE = re.compile(r"\s+(?:and|∧)\s+", re.IGNORECASE)

_REL_OPS = (
    ("<=", Le),
    (">=", Ge),
    ("!=", Ne),
    ("=", Eq),
    ("<", Lt),
    (">", Gt),
)

_ANSWER_SET_TOKENS: dict[str, Set] = {
    EMPTY_SET_TOKEN: S.EmptySet,
    REALS_TOKEN: S.Reals,
}

_REL_SPLIT_RE = re.compile(r"<=|>=|!=|=|<|>")
_REL_CHAIN_RE = re.compile(r"(<=|>=|!=|=|<|>)")

_COMPOUND_RE = re.compile(
    r"^(?P<a>.+?)\s*(?P<op1><=|>=|<|>)\s*(?P<b>.+?)\s*(?P<op2><=|>=|<|>)\s*(?P<c>.+)$"
)

_FUNC_ASSIGN_RE = re.compile(
    r"^(?P<lhs>"
    r"y'|"
    r"y|"
    r"[fg]'\s*\(\s*[a-zA-Z_]\w*\s*\)|"
    # Combined functions only: (f+g)(x), (f∘g)(x) — not a factor like (x-1)(x).
    r"\(\s*[fg](?:\s*[-+*/.∘o]?\s*[fg])*\s*\)\s*\(\s*[a-zA-Z_]\w*\s*\)|"
    r"[fg]\s*\(\s*(?:[a-zA-Z_]\w*|-?\d+(?:\.\d+)?)\s*\)"
    r")\s*=\s*(?P<rhs>.+)$",
    re.IGNORECASE,
)

# f(1)=2 / g(a)=L — point may be numeric or symbolic
_FUNC_VALUE_EQ_RE = re.compile(
    r"^[fg]\s*\(\s*(?P<point>.+?)\s*\)\s*=\s*(?P<rhs>.+)$",
    re.IGNORECASE,
)

_LIMIT_TOKEN_RE = re.compile(
    r"^LIMIT\((?P<body>.*)\)$",
    re.DOTALL,
)

_DIFF_TOKEN_RE = re.compile(
    r"^DIFF\((?P<body>.*)\)$",
    re.DOTALL,
)

_INT_TOKEN_RE = re.compile(
    r"^INT\((?P<body>.*)\)$",
    re.DOTALL,
)

_INTERVAL_TOKEN_RE = re.compile(
    r"^Interval\s*\(",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LimitClaim:
    expr: Expr
    var: Symbol
    point: Expr
    dir: Literal["+", "-", "+-"] = "+-"


@dataclass(frozen=True)
class DerivativeClaim:
    expr: Expr
    var: Symbol


@dataclass(frozen=True)
class IntegralClaim:
    expr: Expr
    var: Symbol
    lower: Expr | None = None
    upper: Expr | None = None


@dataclass(frozen=True)
class MatrixClaim:
    matrix: Matrix


@dataclass(frozen=True)
class ParsedStep:
    kind: Literal[
        "relation",
        "expression",
        "limit",
        "derivative",
        "integral",
        "matrix",
    ]
    value: (
        Boolean
        | Expr
        | Set
        | LimitClaim
        | DerivativeClaim
        | IntegralClaim
        | MatrixClaim
    )


def parse_relation(text: str, symbol: Symbol | None = None) -> Boolean:
    """Parse an equation/inequality (possibly compound or Or) into a SymPy Boolean."""
    step = parse_math_step(text, symbol)
    if step.kind != "relation":
        raise MathParseError(text, "expected a relation, got an expression assignment")
    assert isinstance(step.value, Boolean)
    return step.value


def try_parse_function_value_eq(
    text: str,
    symbol: Symbol | None = None,
) -> tuple[Expr, Expr] | None:
    """If ``text`` looks like ``f(a)=L``, return ``(point, rhs)``; else None."""
    normalized = normalize_math_text(text)
    match = _FUNC_VALUE_EQ_RE.match(normalized)
    if match is None:
        return None

    local_dict: dict[str, object] = {
        "Abs": Abs,
        "sin": sin,
        "cos": cos,
        "tan": tan,
        "oo": oo,
        "ln": log,
        "log": log,
        "exp": exp,
        "e": E,
        "E": E,
    }
    if symbol is not None:
        local_dict[str(symbol)] = symbol

    try:
        point = _parse_side(match.group("point").strip(), local_dict)
        rhs = _parse_side(match.group("rhs").strip(), local_dict)
    except (SyntaxError, TypeError, ValueError, Exception, MathParseError):
        return None
    return point, rhs


def parse_relation_sides(text: str, symbol: Symbol | None = None) -> list[Expr]:
    """Sides of a single (possibly chained) relation, unevaluated as written.

    ``parse_math_step`` collapses a closed relation like ``(-3*(-5))/(...) = 15/7``
    to ``True``; numeric-evaluation checks need the written operands instead.
    """
    normalized = normalize_math_text(text)
    if not normalized:
        raise MathParseError(text, "empty expression")
    if _OR_SPLIT_RE.search(normalized) or _AND_SPLIT_RE.search(normalized):
        raise MathParseError(text, "expected a single relation")
    parts = [part.strip() for part in _REL_SPLIT_RE.split(normalized)]
    if len(parts) < 2 or not all(parts):
        raise MathParseError(text, "no supported relation operator found")
    local_dict = _step_local_dict(symbol)
    try:
        return [_parse_side(part, local_dict) for part in parts]
    except MathParseError:
        raise
    except Exception as exc:
        raise MathParseError(text, str(exc)) from exc


def _step_local_dict(symbol: Symbol | None) -> dict[str, object]:
    local_dict: dict[str, object] = {
        "Abs": Abs,
        "sin": sin,
        "cos": cos,
        "tan": tan,
        "oo": oo,
        "C": Symbol("C"),
        "c": Symbol("C"),
        "ln": log,
        "log": log,
        "exp": exp,
        "e": E,
        "E": E,
        "Interval": Interval,
    }
    if symbol is not None:
        local_dict[str(symbol)] = symbol
    return local_dict


def parse_math_step(text: str, symbol: Symbol | None = None) -> ParsedStep:
    """Parse a student step as relation, expression, limit, derivative, or integral."""
    normalized = normalize_math_text(text)
    if not normalized:
        raise MathParseError(text, "empty expression")

    local_dict = _step_local_dict(symbol)

    candidates = [normalized]
    for part in re.split(r"[;\n]", text):
        part_norm = normalize_math_text(part)
        if part_norm and part_norm not in candidates:
            candidates.append(part_norm)

    errors: list[str] = []
    for candidate in candidates:
        try:
            return _parse_candidate(candidate, local_dict)
        except MathParseError as exc:
            errors.append(str(exc.reason))

    raise MathParseError(text, errors[-1] if errors else "parse failed")


def _parse_candidate(
    normalized: str,
    local_dict: dict[str, object],
) -> ParsedStep:
    matrix_step = _try_parse_matrix_expr(normalized, local_dict)
    if matrix_step is not None:
        return matrix_step

    limit_step = _try_parse_limit_token(normalized, local_dict)
    if limit_step is not None:
        return limit_step

    diff_step = _try_parse_diff_token(normalized, local_dict)
    if diff_step is not None:
        return diff_step

    int_step = _try_parse_int_token(normalized, local_dict)
    if int_step is not None:
        return int_step

    answer_set = _ANSWER_SET_TOKENS.get(normalized.strip())
    if answer_set is not None:
        return ParsedStep(kind="expression", value=answer_set)

    interval_step = _try_parse_interval_expr(normalized, local_dict)
    if interval_step is not None:
        return interval_step

    assign = _FUNC_ASSIGN_RE.match(normalized)
    if assign is not None:
        assigned = _try_parse_assignment(assign, local_dict)
        if assigned is not None:
            return ParsedStep(kind="expression", value=assigned)
        normalized, local_dict = _opaque_assignment_lhs(assign, normalized, local_dict)

    # Bare scalar / short algebraic expression (e.g. final answer "2"), not prose.
    if not any(op in normalized for op, _ in _REL_OPS):
        if _looks_like_math_expression(normalized):
            try:
                expr = _parse_side(normalized, local_dict)
                return ParsedStep(kind="expression", value=expr)
            except (SyntaxError, TypeError, ValueError, Exception):
                pass

    return ParsedStep(
        kind="relation",
        value=_parse_proposition(normalized, local_dict),
    )


def _try_parse_assignment(
    assign: re.Match[str],
    local_dict: dict[str, object],
) -> Expr | None:
    """RHS of ``f(x) = ...`` / ``y = ...``; ``None`` means "read it as a relation".

    ``y = 2 or y = 3`` and ``f(0) = -1/2 < 0`` are claims about values, and a
    bare ``y = 3`` is a root of ``y``, not the function ``y(x) = 3``.
    """
    try:
        expr = _parse_side(assign.group("rhs").strip(), local_dict)
    except (SyntaxError, TypeError, ValueError, Exception):
        return None
    if not isinstance(expr, Expr):
        return None
    if assign.group("lhs").strip() == "y" and not (expr.free_symbols - {Symbol("y")}):
        return None
    return expr


_OPAQUE_LHS_NAME = "AssignedValue"


def _opaque_assignment_lhs(
    assign: re.Match[str],
    normalized: str,
    local_dict: dict[str, object],
) -> tuple[str, dict[str, object]]:
    """Keep ``f(0)`` as an unknown value; read literally it is ``f*0 = 0``."""
    lhs = assign.group("lhs").strip()
    if lhs == "y":
        return normalized, local_dict
    return (
        _OPAQUE_LHS_NAME + normalized[assign.end("lhs"):],
        {**local_dict, _OPAQUE_LHS_NAME: Symbol(lhs)},
    )


def _try_parse_matrix_expr(
    normalized: str,
    local_dict: dict[str, object],
) -> ParsedStep | None:
    """Parse MATRIX / TRANSPOSE / DET / INV / NORM / DOT into matrix or scalar."""
    if not any(
        tok in normalized
        for tok in ("MATRIX(", "TRANSPOSE(", "DET(", "INV(", "NORM(", "DOT(")
    ):
        return None

    code = normalized.strip()
    # Strip optional assignment already handled in normalize; allow trailing noise
    code = re.sub(r"\\times|\\cdot", "*", code)
    code = code.replace("MATRIX(", "Matrix(")

    def _as_matrix(value: object) -> Matrix:
        if isinstance(value, Matrix):
            return value
        return Matrix(value)  # type: ignore[arg-type]

    def _transpose(value: object) -> Matrix:
        return _as_matrix(value).T

    def _det(value: object) -> Expr:
        return _as_matrix(value).det()  # type: ignore[return-value]

    def _inv(value: object) -> Matrix:
        return _as_matrix(value).inv()

    def _norm(value: object) -> Expr:
        return _as_matrix(value).norm()  # type: ignore[return-value]

    def _dot(left: object, right: object) -> Expr:
        return _as_matrix(left).dot(_as_matrix(right))  # type: ignore[return-value]

    env: dict[str, object] = {
        "Matrix": Matrix,
        "TRANSPOSE": _transpose,
        "DET": _det,
        "INV": _inv,
        "NORM": _norm,
        "DOT": _dot,
        "Abs": Abs,
        "oo": oo,
    }
    env.update(local_dict)
    try:
        result = eval(code, {"__builtins__": {}}, env)  # noqa: S307
    except Exception as exc:
        raise MathParseError(normalized, f"matrix parse failed: {exc}") from exc

    if isinstance(result, Matrix):
        return ParsedStep(kind="matrix", value=MatrixClaim(matrix=result))

    # Determinant / norm / dot (and similar) evaluate to a scalar Expr / number
    if isinstance(result, bool):
        raise MathParseError(normalized, "unexpected boolean from matrix expression")
    if isinstance(result, int):
        return ParsedStep(kind="expression", value=Integer(result))
    if isinstance(result, Expr) or getattr(result, "is_number", False):
        return ParsedStep(kind="expression", value=result)  # type: ignore[arg-type]

    raise MathParseError(
        normalized,
        "matrix expression did not evaluate to Matrix or scalar",
    )


_COMMA_TUPLE_RE = re.compile(
    r"[\(\[][^\)\]]*,[^\)\]]*[\)\]]"
)


def _looks_like_math_expression(normalized: str) -> bool:
    """Reject multi-word prose; accept numbers and compact algebra."""
    # Interval / tuple shapes must not take the bare-expression fast path
    # (implicit mul would build Mul(Tuple) and emit SymPy deprecation).
    if _COMMA_TUPLE_RE.search(normalized):
        return False
    if re.fullmatch(r"[\d\.]+", normalized):
        return True
    if re.search(r"[\+\-\*/\^]", normalized):
        return True
    if re.fullmatch(r"[a-zA-Z_]\w*(?:\([^)]*\))?", normalized):
        return True
    # Multi-word Indonesian/English prose → not an expression step
    if " " in normalized:
        return False
    return bool(re.fullmatch(r"[\w\(\)\.]+", normalized))


def _try_parse_limit_token(
    normalized: str,
    local_dict: dict[str, object],
) -> ParsedStep | None:
    match = _LIMIT_TOKEN_RE.match(normalized.strip())
    if match is None:
        return None
    body = match.group("body").strip()
    # Split from the right: expr may contain commas (rare); expect 4 fields.
    # Format: expr, var, point, dir
    parts = _split_limit_body(body)
    if parts is None:
        raise MathParseError(normalized, "invalid LIMIT token")
    expr_raw, var_raw, point_raw, dir_raw = parts
    direction: Literal["+", "-", "+-"]
    if dir_raw in ("+", "-", "+-"):
        direction = dir_raw  # type: ignore[assignment]
    else:
        direction = "+-"
    try:
        var = Symbol(var_raw)
        local = dict(local_dict)
        local[str(var)] = var
        expr = _parse_side(expr_raw, local)
        point = _parse_side(point_raw, local)
    except (SyntaxError, TypeError, ValueError, Exception) as exc:
        raise MathParseError(normalized, str(exc)) from exc
    return ParsedStep(
        kind="limit",
        value=LimitClaim(expr=expr, var=var, point=point, dir=direction),
    )


def _try_parse_diff_token(
    normalized: str,
    local_dict: dict[str, object],
) -> ParsedStep | None:
    match = _DIFF_TOKEN_RE.match(normalized.strip())
    if match is None:
        return None
    body = match.group("body").strip()
    parts = _split_diff_body(body)
    if parts is None:
        raise MathParseError(normalized, "invalid DIFF token")
    expr_raw, var_raw = parts
    try:
        var = Symbol(var_raw)
        local = dict(local_dict)
        local[str(var)] = var
        expr = _parse_side(expr_raw, local)
    except (SyntaxError, TypeError, ValueError, Exception) as exc:
        raise MathParseError(normalized, str(exc)) from exc
    return ParsedStep(
        kind="derivative",
        value=DerivativeClaim(expr=expr, var=var),
    )


def _try_parse_int_token(
    normalized: str,
    local_dict: dict[str, object],
) -> ParsedStep | None:
    match = _INT_TOKEN_RE.match(normalized.strip())
    if match is None:
        return None
    body = match.group("body").strip()
    parts = _split_int_body(body)
    if parts is None:
        raise MathParseError(normalized, "invalid INT token")
    try:
        var = Symbol(parts[1])
        local = dict(local_dict)
        local[str(var)] = var
        expr = _parse_side(parts[0], local)
        lower: Expr | None = None
        upper: Expr | None = None
        if len(parts) == 4:
            lower = _parse_side(parts[2], local)
            upper = _parse_side(parts[3], local)
    except (SyntaxError, TypeError, ValueError, Exception) as exc:
        raise MathParseError(normalized, str(exc)) from exc
    return ParsedStep(
        kind="integral",
        value=IntegralClaim(expr=expr, var=var, lower=lower, upper=upper),
    )


def _try_parse_interval_expr(
    normalized: str,
    local_dict: dict[str, object],
) -> ParsedStep | None:
    """Parse ``Interval(a, b)`` / kwargs form as a set expression."""
    stripped = normalized.strip()
    if not _INTERVAL_TOKEN_RE.match(stripped):
        return None
    code = re.sub(r"(?i)^interval\s*\(", "Interval(", stripped, count=1)
    env = dict(local_dict)
    env["Interval"] = Interval
    env.setdefault("oo", oo)
    env.setdefault("True", True)
    env.setdefault("False", False)
    try:
        # Bypass _parse_side comma preflight (Interval args contain commas).
        result = parse_expr(
            code,
            local_dict=env,
            transformations=_TRANSFORMATIONS,
            evaluate=True,
        )
    except (SyntaxError, TypeError, ValueError, Exception) as exc:
        raise MathParseError(normalized, str(exc)) from exc
    if not isinstance(result, Interval):
        raise MathParseError(normalized, "expected Interval expression")
    return ParsedStep(kind="expression", value=result)


def _split_diff_body(body: str) -> tuple[str, str] | None:
    """Split ``expr, var`` allowing commas inside nested parens in expr."""
    depth = 0
    commas: list[int] = []
    for index, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            commas.append(index)
    if not commas:
        return None
    last = commas[-1]
    expr = body[:last].strip()
    var = body[last + 1 :].strip()
    if not expr or not var:
        return None
    return expr, var


def _split_int_body(body: str) -> tuple[str, ...] | None:
    """Split ``expr, var`` or ``expr, var, a, b`` (commas outside nested parens)."""
    depth = 0
    commas: list[int] = []
    for index, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            commas.append(index)
    if len(commas) == 1:
        expr = body[: commas[0]].strip()
        var = body[commas[0] + 1 :].strip()
        if expr and var:
            return expr, var
        return None
    if len(commas) == 3:
        e0, e1, e2 = commas
        expr = body[:e0].strip()
        var = body[e0 + 1 : e1].strip()
        lower = body[e1 + 1 : e2].strip()
        upper = body[e2 + 1 :].strip()
        if expr and var and lower and upper:
            return expr, var, lower, upper
        return None
    return None


def _split_limit_body(body: str) -> tuple[str, str, str, str] | None:
    """Split ``expr, var, point, dir`` allowing commas inside nested parens in expr."""
    depth = 0
    commas: list[int] = []
    for index, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            commas.append(index)
    if len(commas) < 3:
        return None
    # Last three commas separate var, point, dir
    c1, c2, c3 = commas[-3], commas[-2], commas[-1]
    expr = body[:c1].strip()
    var = body[c1 + 1 : c2].strip()
    point = body[c2 + 1 : c3].strip()
    direction = body[c3 + 1 :].strip()
    if not expr or not var or not point or not direction:
        return None
    return expr, var, point, direction


def _parse_proposition(
    normalized: str,
    local_dict: dict[str, object],
) -> Boolean:
    or_parts = [p.strip() for p in _OR_SPLIT_RE.split(normalized) if p.strip()]
    if len(or_parts) > 1:
        return Or(*(_parse_and_proposition(part, local_dict) for part in or_parts))
    return _parse_and_proposition(normalized, local_dict)


def _parse_and_proposition(
    normalized: str,
    local_dict: dict[str, object],
) -> Boolean:
    and_parts = [p.strip() for p in _AND_SPLIT_RE.split(normalized) if p.strip()]
    if len(and_parts) > 1:
        return And(*(_parse_atomic_proposition(part, local_dict) for part in and_parts))
    return _parse_atomic_proposition(normalized, local_dict)


def _parse_atomic_proposition(
    normalized: str,
    local_dict: dict[str, object],
) -> Boolean:
    compound = _try_parse_compound(normalized, local_dict)
    if compound is not None:
        return compound
    chain = _try_parse_chain(normalized, local_dict)
    if chain is not None:
        return chain
    return _parse_single_relation(normalized, local_dict)


def _try_parse_chain(
    normalized: str,
    local_dict: dict[str, object],
) -> Boolean | None:
    """``A = B < 0`` (sign-test layout) → ``A = B and B < 0``; needs an ``=`` link."""
    tokens = [token.strip() for token in _REL_CHAIN_RE.split(normalized)]
    sides, ops = tokens[0::2], tokens[1::2]
    if len(sides) < 3 or "=" not in ops or not all(sides):
        return None
    try:
        parsed = [_parse_side(side, local_dict) for side in sides]
    except (SyntaxError, TypeError, ValueError, Exception):
        return None
    constructors = dict(_REL_OPS)
    return And(
        *(
            constructors[op](left, right)
            for op, left, right in zip(ops, parsed, parsed[1:])
        )
    )


def _try_parse_compound(
    normalized: str,
    local_dict: dict[str, object],
) -> Boolean | None:
    match = _COMPOUND_RE.match(normalized)
    if match is None:
        return None
    op1 = match.group("op1")
    op2 = match.group("op2")
    if not (
        (op1 in ("<", "<=") and op2 in ("<", "<="))
        or (op1 in (">", ">=") and op2 in (">", ">="))
    ):
        return None
    a_raw, b_raw, c_raw = match.group("a"), match.group("b"), match.group("c")
    if any(op in b_raw for op, _ in _REL_OPS):
        return None
    try:
        a = _parse_side(a_raw.strip(), local_dict)
        b = _parse_side(b_raw.strip(), local_dict)
        c = _parse_side(c_raw.strip(), local_dict)
    except (SyntaxError, TypeError, ValueError, Exception):
        return None
    ctor1 = dict(_REL_OPS)[op1]
    ctor2 = dict(_REL_OPS)[op2]
    return And(ctor1(a, b), ctor2(b, c))


def _parse_single_relation(
    normalized: str,
    local_dict: dict[str, object],
) -> Relational:
    for op, constructor in _REL_OPS:
        if op not in normalized:
            continue
        left_raw, right_raw = normalized.split(op, 1)
        left_raw = left_raw.strip()
        right_raw = right_raw.strip()
        if not left_raw or not right_raw:
            continue
        if any(other in left_raw for other, _ in _REL_OPS if other != op):
            continue
        try:
            left = _parse_side(left_raw, local_dict)
            right = _parse_side(right_raw, local_dict)
            return constructor(left, right)
        except (SyntaxError, TypeError, ValueError, Exception) as exc:
            raise MathParseError(normalized, str(exc)) from exc

    raise MathParseError(normalized, "no supported relation operator found")


def _expr_contains_tuple(expr: object) -> bool:
    """True if ``expr`` is or embeds a SymPy Tuple (unsafe with Mul)."""
    if type(expr).__name__ == "Tuple":
        return True
    if isinstance(expr, (tuple, list)):
        return True
    args = getattr(expr, "args", None)
    if not args:
        return False
    return any(_expr_contains_tuple(arg) for arg in args)


def _parse_side(side: str, local_dict: dict[str, object]) -> Expr:
    stripped = side.strip()
    # Preflight: never call parse_expr on comma-tuples / juxtaposed intervals —
    # implicit_multiplication would emit SymPyDeprecationWarning (Mul+Tuple).
    # Juxtaposed factors without commas, e.g. (x-1)(x+2), are ordinary products.
    if _COMMA_TUPLE_RE.search(stripped):
        raise MathParseError(side, "tuple/interval is not an algebraic expression")
    result = parse_expr(
        stripped,
        local_dict=local_dict,
        transformations=_TRANSFORMATIONS,
        evaluate=False,
    )
    if _expr_contains_tuple(result):
        raise MathParseError(side, "tuple/interval is not an algebraic expression")
    if not isinstance(result, Expr):
        raise MathParseError(side, f"expected expression, got {type(result).__name__}")
    return result


def default_symbol() -> Symbol:
    return Symbol("x")


_NON_VARIABLE_NAMES = frozenset({"C", "E", "I"})


def _variable_candidates(step: ParsedStep, text: str) -> set[str]:
    """Single-letter free symbols that the student actually wrote in ``text``.

    Bare intervals are rewritten with ``x`` during normalize; such an ``x``
    is not counted unless the letter appears in the source text.
    """
    free = getattr(step.value, "free_symbols", None) or set()
    return {
        str(sym)
        for sym in free
        if len(str(sym)) == 1
        and str(sym) not in _NON_VARIABLE_NAMES
        and str(sym) in text
    }


def infer_main_symbol(texts: Iterable[str]) -> Symbol:
    """Most frequent written variable across ``texts``; ``x`` on ties or when none."""
    counts: Counter[str] = Counter()
    default = default_symbol()
    for text in texts:
        if not (text or "").strip():
            continue
        try:
            step = parse_math_step(text, default)
        except MathParseError:
            continue
        counts.update(_variable_candidates(step, text))
    if not counts:
        return default
    best = max(counts.values())
    leaders = sorted(name for name, count in counts.items() if count == best)
    return default if str(default) in leaders else Symbol(leaders[0])


def rebind_default_symbol(step: ParsedStep, text: str, symbol: Symbol) -> ParsedStep:
    """Swap the normalize-injected ``x`` (bare intervals) for the question's variable."""
    default = default_symbol()
    if symbol == default or step.kind not in ("relation", "expression"):
        return step
    free = getattr(step.value, "free_symbols", None) or set()
    if free != {default} or str(default) in text:
        return step
    return ParsedStep(kind=step.kind, value=step.value.subs(default, symbol))  # type: ignore[union-attr]
