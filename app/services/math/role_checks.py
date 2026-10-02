"""SymPy checks for role-specific steps (zero-makers, closed numeric evaluations)."""

from __future__ import annotations

from collections.abc import Sequence

from sympy import (
    Expr,
    FiniteSet,
    Number,
    S,
    Symbol,
    Union,
    fraction,
    nan,
    oo,
    simplify,
    solveset,
    together,
    zoo,
)
from sympy.core.relational import Relational
from sympy.logic.boolalg import Boolean
from sympy.sets.sets import Set

from app.services.math.equivalence import solution_set


def finite_solutions(proposition: Boolean, symbol: Symbol) -> Set | None:
    """Real solutions when they form a finite (possibly empty) set, else ``None``."""
    try:
        values = solution_set(proposition, symbol)
    except Exception:
        return None
    if values is S.EmptySet or isinstance(values, FiniteSet):
        return values
    return None


def zero_makers(proposition: Boolean, symbol: Symbol) -> Set | None:
    """Real zeros of the numerator and denominator of ``lhs - rhs``."""
    if not isinstance(proposition, Relational):
        return None
    try:
        numerator, denominator = fraction(together(proposition.lhs - proposition.rhs))
        zeros = Union(
            solveset(numerator, symbol, domain=S.Reals),
            solveset(denominator, symbol, domain=S.Reals),
        )
    except Exception:
        return None
    if zeros is S.EmptySet or isinstance(zeros, FiniteSet):
        return zeros
    return None


def values_are_zero_makers(
    values: Set,
    reference: Boolean,
    symbol: Symbol,
) -> bool | None:
    """Whether every stated value zeroes the reference numerator or denominator."""
    targets = zero_makers(reference, symbol)
    if targets is None:
        return None
    try:
        return bool(values.is_subset(targets))
    except Exception:
        return None


def numeric_eval_matches_reference(
    sides: Sequence[Expr],
    reference: Boolean,
    symbol: Symbol,
) -> bool | None:
    """Whether a written side equals the reference expression at a number the student wrote.

    ``sides`` are the unevaluated operands of the student's closed relation.
    Candidate expressions are ``lhs - rhs``, ``lhs`` and ``rhs`` of the reference
    (those containing ``symbol``); test points are the numbers written (and their
    negations). ``None`` when there is nothing to compare against.
    """
    if not isinstance(reference, Relational) or not sides:
        return None
    candidates = [
        expr
        for expr in (reference.lhs - reference.rhs, reference.lhs, reference.rhs)
        if symbol in expr.free_symbols
    ]
    if not candidates:
        return None
    points: set[Expr] = set()
    for side in sides:
        for atom in side.atoms(Number):
            points.update((atom, -atom))
    try:
        # A literal ``0`` is just the comparison bound and would match ``f(0) = 0``.
        values = [
            simplify(side) for side in sides if not (side.is_Number and side == 0)
        ]
        for expr in candidates:
            for point in points:
                image = simplify(expr.subs(symbol, point))
                if image.has(zoo, nan, oo, -oo):
                    continue
                if any(simplify(value - image) == 0 for value in values):
                    return True
    except Exception:
        return None
    return False


def numeric_relation_holds(proposition: Boolean) -> bool | None:
    """Truth of a relation without free symbols; ``None`` when a symbol remains."""
    if getattr(proposition, "free_symbols", None):
        return None
    try:
        reduced = simplify(proposition)
    except Exception:
        return None
    if reduced is S.true:
        return True
    if reduced is S.false:
        return False
    return None
