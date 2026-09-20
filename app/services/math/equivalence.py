"""SymPy solution-set, expression, limit, derivative, and integral equivalence."""

from __future__ import annotations

from sympy import (
    Add,
    And,
    ConditionSet,
    Expr,
    Integral as SymIntegral,
    Intersection,
    Or,
    S,
    Symbol,
    Union,
    diff,
    exp,
    expand_log,
    fraction,
    integrate,
    limit,
    log,
    oo,
    powsimp,
    simplify,
    solveset,
    together,
    zoo,
)
from sympy.core.relational import Relational
from sympy.logic.boolalg import Boolean
from sympy.functions.elementary.exponential import ExpBase

from app.services.math.parser import (
    DerivativeClaim,
    IntegralClaim,
    LimitClaim,
    MatrixClaim,
)


def solution_set(proposition: Boolean, symbol: Symbol):
    """Return the real solution set of a Relational / And / Or proposition."""
    if isinstance(proposition, Relational):
        return solveset(proposition, symbol, domain=S.Reals)
    if isinstance(proposition, And):
        sets = [_atomic_solution_set(arg, symbol) for arg in proposition.args]
        return Intersection(*sets)
    if isinstance(proposition, Or):
        sets = [_atomic_solution_set(arg, symbol) for arg in proposition.args]
        return Union(*sets)
    return solveset(proposition, symbol, domain=S.Reals)


def _atomic_solution_set(arg: Boolean, symbol: Symbol):
    if isinstance(arg, (And, Or)):
        return solution_set(arg, symbol)
    if isinstance(arg, Relational):
        return solveset(arg, symbol, domain=S.Reals)
    return solveset(arg, symbol, domain=S.Reals)


def relations_equivalent(
    previous: Boolean,
    current: Boolean,
    symbol: Symbol,
) -> bool | None:
    """Compare solution sets of two propositions."""
    try:
        prev_set = solution_set(previous, symbol)
        curr_set = solution_set(current, symbol)
    except Exception:
        return None

    if isinstance(prev_set, ConditionSet) or isinstance(curr_set, ConditionSet):
        return None

    try:
        return bool(prev_set == curr_set)
    except Exception:
        return None


def _has_log_or_exp(expr: Expr) -> bool:
    return bool(expr.has(log, exp, ExpBase))


def expressions_equivalent(previous: Expr, current: Expr) -> bool | None:
    """Compare algebraic expressions via simplify(previous - current) == 0."""
    try:
        delta = simplify(previous - current)
        if delta == 0:
            return True
        if delta.is_number and delta != 0:
            return False
        expanded = simplify(delta.expand())
        if expanded == 0:
            return True
        if expanded.is_number and expanded != 0:
            return False

        if _has_log_or_exp(previous) or _has_log_or_exp(current):
            try:
                left = expand_log(powsimp(previous, force=True), force=True)
                right = expand_log(powsimp(current, force=True), force=True)
                log_delta = simplify(left - right)
                if log_delta == 0:
                    return True
                if log_delta.is_number and log_delta != 0:
                    return False
            except Exception:
                pass

        if expanded.free_symbols and expanded != 0:
            return False
        return None
    except Exception:
        return None


def evaluate_limit(claim: LimitClaim) -> Expr | None:
    """Evaluate a limit; return None if result is infinite or undecidable.

    Finite approach points and ``±∞`` approach are both allowed when the
    evaluated limit itself is finite (e.g. ``lim x→∞ 1/x = 0``).
    """
    try:
        kwargs: dict[str, str] = {}
        if claim.dir in ("+", "-"):
            kwargs["dir"] = claim.dir
        result = limit(claim.expr, claim.var, claim.point, **kwargs)
        if result in (oo, -oo, zoo) or getattr(result, "is_infinite", False):
            return None
        return result
    except Exception:
        return None


def limits_equivalent(
    previous: LimitClaim,
    current: LimitClaim | Expr,
) -> bool | None:
    """Compare two limits, or a limit against a scalar/expression value."""
    prev_val = evaluate_limit(previous)
    if prev_val is None:
        return None

    if isinstance(current, LimitClaim):
        curr_val = evaluate_limit(current)
        if curr_val is None:
            return None
        return expressions_equivalent(prev_val, curr_val)

    return expressions_equivalent(prev_val, current)


def point_value(expr: Expr, var: Symbol, point: Expr) -> Expr | None:
    """Evaluate ``expr`` at ``var = point``; None if undefined or fails."""
    try:
        if point in (oo, -oo) or (hasattr(point, "has") and point.has(oo)):
            return None
        _num, den = fraction(together(expr))
        den_at = simplify(den.subs(var, point))
        if den_at == 0:
            return None
        value = simplify(expr.subs(var, point))
        if value in (oo, -oo, zoo) or getattr(value, "is_infinite", False):
            return None
        if value.has(zoo) or value == S.NaN:
            return None
        return value
    except Exception:
        return None


def continuity_limit_equals_value(
    claim: LimitClaim,
    claimed_value: Expr,
    *,
    claimed_point: Expr | None = None,
) -> bool | None:
    """Check lim = claimed value, and f(a) plug-in when defined.

    If ``claimed_point`` is given it must match ``claim.point``.
    When the expression is undefined at the point (removable hole) but the
    limit equals ``claimed_value``, return True (continuous extension).
    """
    if claimed_point is not None:
        point_match = expressions_equivalent(claimed_point, claim.point)
        if point_match is False:
            return False
        if point_match is None:
            return None

    lim_match = limits_equivalent(claim, claimed_value)
    if lim_match is not True:
        return lim_match

    plug = point_value(claim.expr, claim.var, claim.point)
    if plug is None:
        return True
    return expressions_equivalent(plug, claimed_value)


def evaluate_derivative(claim: DerivativeClaim) -> Expr | None:
    """Differentiate ``claim.expr`` w.r.t. ``claim.var``; None if undecidable."""
    try:
        return simplify(diff(claim.expr, claim.var))
    except Exception:
        return None


def derivatives_equivalent(
    previous: DerivativeClaim,
    current: DerivativeClaim | Expr,
) -> bool | None:
    """Compare two derivative claims, or a derivative against an expression."""
    prev_val = evaluate_derivative(previous)
    if prev_val is None:
        return None

    if isinstance(current, DerivativeClaim):
        curr_val = evaluate_derivative(current)
        if curr_val is None:
            return None
        return expressions_equivalent(prev_val, curr_val)

    return expressions_equivalent(prev_val, current)


def strip_constant_of_integration(expr: Expr) -> Expr:
    """Drop additive ``±C`` / ``k*C`` terms (integration constant only)."""
    c_names = {"C", "c"}

    def _is_pure_c(term: Expr) -> bool:
        symbols = term.free_symbols
        return bool(symbols) and all(str(sym) in c_names for sym in symbols)

    if _is_pure_c(expr):
        return S.Zero
    if not isinstance(expr, Add):
        return expr
    kept = [term for term in expr.args if not _is_pure_c(term)]
    if not kept:
        return S.Zero
    return Add(*kept)


def evaluate_integral(claim: IntegralClaim) -> Expr | None:
    """Integrate ``claim``; None if undecidable or infinite."""
    try:
        if claim.lower is not None and claim.upper is not None:
            if claim.lower in (oo, -oo) or claim.upper in (oo, -oo):
                return None
            if (hasattr(claim.lower, "has") and claim.lower.has(oo)) or (
                hasattr(claim.upper, "has") and claim.upper.has(oo)
            ):
                return None
            result = integrate(claim.expr, (claim.var, claim.lower, claim.upper))
        else:
            result = integrate(claim.expr, claim.var)
        result = simplify(result)
        if result in (oo, -oo, zoo) or getattr(result, "is_infinite", False):
            return None
        if isinstance(result, SymIntegral):
            return None
        return result
    except Exception:
        return None


def integrals_equivalent(
    previous: IntegralClaim,
    current: IntegralClaim | Expr,
) -> bool | None:
    """Compare two integral claims, or an integral against an expression (+C ok)."""
    prev_val = evaluate_integral(previous)
    if prev_val is None:
        return None
    prev_val = strip_constant_of_integration(prev_val)

    if isinstance(current, IntegralClaim):
        curr_val = evaluate_integral(current)
        if curr_val is None:
            return None
        return expressions_equivalent(
            prev_val,
            strip_constant_of_integration(curr_val),
        )

    return expressions_equivalent(
        prev_val,
        strip_constant_of_integration(current),
    )


def matrices_equivalent(
    previous: MatrixClaim,
    current: MatrixClaim,
) -> bool | None:
    """Compare two evaluated matrices element-wise."""
    try:
        left = previous.matrix
        right = current.matrix
        if left.shape != right.shape:
            return False
        diff = simplify(left - right)
        if diff == left.zeros(*left.shape):
            return True
        # Any non-zero numeric entry → False; undecidable symbols → None
        undecided = False
        for entry in diff:
            entry_s = simplify(entry)
            if entry_s == 0:
                continue
            if entry_s.is_number and entry_s != 0:
                return False
            undecided = True
        if undecided:
            return None
        return True
    except Exception:
        return None

