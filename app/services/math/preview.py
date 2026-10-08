"""How SymPy reads a ``symbolic.repr`` while the user reviews a transcription."""

from __future__ import annotations

from sympy import Basic, latex

from app.exceptions import MathParseError
from app.services.math.parser import parse_math_step


def symbolic_preview_latex(text: str) -> str | None:
    """LaTeX of the parsed step, or ``None`` when SymPy cannot read it.

    ``None`` is the useful signal here: the validator will not be able to check
    that step either.
    """
    if not text.strip():
        return None
    try:
        step = parse_math_step(text)
    except (MathParseError, ValueError, TypeError):
        return None
    if not isinstance(step.value, Basic):
        return None
    return latex(step.value)
