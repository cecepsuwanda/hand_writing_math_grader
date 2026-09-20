"""SymPy solution-set equivalence for relations."""

from __future__ import annotations

from sympy import ConditionSet, S, Symbol, solveset
from sympy.core.relational import Relational


def solution_set(relation: Relational, symbol: Symbol):
    """Return the real solution set of a relation in ``symbol``."""
    return solveset(relation, symbol, domain=S.Reals)


def relations_equivalent(
    previous: Relational,
    current: Relational,
    symbol: Symbol,
) -> bool | None:
    """Compare solution sets of two relations.

    Returns:
        True if sets are equal, False if both decidable and unequal,
        None if SymPy cannot decide (ConditionSet / error).
    """
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
