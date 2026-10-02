"""SymPy checks for role-specific steps (zero-makers, closed numeric evaluations)."""

from __future__ import annotations

from sympy import FiniteSet, S, Symbol, Union, fraction, simplify, solveset, together
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
