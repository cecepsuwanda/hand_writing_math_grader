"""Compare student final answer to standard solution via SymPy equivalence."""

from __future__ import annotations

import logging
from pathlib import Path

from sympy import Expr, Symbol
from sympy.logic.boolalg import Boolean

from app.exceptions import MathParseError
from app.functions.standard_extract import (
    extract_final_answer_from_tex,
    extract_solution_steps_from_tex,
    standard_solution_path,
)
from app.models.question import Question, StudentStep
from app.models.validation import ValidationStatus
from app.services.math.equivalence import (
    derivatives_equivalent,
    expressions_equivalent,
    integrals_equivalent,
    limits_equivalent,
    matrices_equivalent,
    relations_equivalent,
)
from app.services.math.parser import (
    DerivativeClaim,
    IntegralClaim,
    LimitClaim,
    MatrixClaim,
    ParsedStep,
    default_symbol,
    parse_math_step,
)

logger = logging.getLogger(__name__)


class StandardFinalComparer:
    """Load ``solutions/question_NNN.tex`` and compare finals mathematically."""

    def __init__(
        self,
        standard_dir: Path,
        symbol: Symbol | None = None,
    ) -> None:
        self._standard_dir = Path(standard_dir)
        self._symbol = symbol or default_symbol()

    def compare(
        self,
        question: Question,
    ) -> tuple[ValidationStatus, str] | None:
        """Return (status, reason), or None if no standard solution file."""
        path = standard_solution_path(
            self._standard_dir, question.question_number
        )
        if not path.is_file():
            return None

        try:
            tex = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read standard solution %s: %s", path, exc)
            return ValidationStatus.UNCERTAIN, f"could not read standard solution: {path}"

        standard_text = extract_final_answer_from_tex(tex)
        if not standard_text:
            return (
                ValidationStatus.UNCERTAIN,
                f"no % final answer marker in {path.name}",
            )

        student_text = self._student_final_text(question)
        if not student_text:
            return ValidationStatus.INVALID, "student final answer is empty"

        try:
            student_step = parse_math_step(student_text, self._symbol)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse student final answer for standard compare",
            )

        try:
            standard_step = parse_math_step(standard_text, self._symbol)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse standard final answer",
            )

        result = self._equivalent(student_step, standard_step)
        if result is True:
            return ValidationStatus.VALID, "final answer matches standard"
        if result is False:
            return ValidationStatus.INVALID, "final answer differs from standard"
        return (
            ValidationStatus.UNCERTAIN,
            "SymPy could not decide final vs standard equivalence",
        )

    def compare_steps(
        self,
        question: Question,
    ) -> dict[int, tuple[ValidationStatus, str]] | None:
        """Sequential index align of student steps to standard solution rows.

        Returns None if the solution file is missing. Student steps beyond the
        standard step count are omitted (consistency-only scoring).
        """
        path = standard_solution_path(
            self._standard_dir, question.question_number
        )
        if not path.is_file():
            return None

        try:
            tex = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read standard solution %s: %s", path, exc)
            steps = sorted(question.student_steps, key=lambda s: s.step_number)
            return {
                step.step_number: (
                    ValidationStatus.UNCERTAIN,
                    f"could not read standard solution: {path}",
                )
                for step in steps
            }

        standard_texts = extract_solution_steps_from_tex(tex)
        if not standard_texts:
            return {}

        student_steps = sorted(question.student_steps, key=lambda s: s.step_number)
        results: dict[int, tuple[ValidationStatus, str]] = {}
        for index, step in enumerate(student_steps):
            if index >= len(standard_texts):
                break
            results[step.step_number] = self._compare_step_pair(
                step, standard_texts[index]
            )
        return results

    def _compare_step_pair(
        self,
        step: StudentStep,
        standard_text: str,
    ) -> tuple[ValidationStatus, str]:
        student_text = (step.latex or "").strip() or (step.raw_text or "").strip()
        if not student_text:
            return ValidationStatus.INVALID, "student step is empty"

        try:
            student_parsed = parse_math_step(student_text, self._symbol)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse student step for standard align",
            )

        try:
            standard_parsed = parse_math_step(standard_text, self._symbol)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse standard step for align",
            )

        result = self._equivalent(student_parsed, standard_parsed)
        if result is True:
            return ValidationStatus.VALID, "step matches standard"
        if result is False:
            return ValidationStatus.INVALID, "step differs from standard"
        return (
            ValidationStatus.UNCERTAIN,
            "SymPy could not decide step vs standard equivalence",
        )

    def _student_final_text(self, question: Question) -> str:
        final = (question.student_final_answer or "").strip()
        if final:
            return final
        if not question.student_steps:
            return ""
        last = max(question.student_steps, key=lambda s: s.step_number)
        latex = (last.latex or "").strip()
        if latex:
            return latex
        return (last.raw_text or "").strip()

    def _equivalent(
        self,
        student: ParsedStep,
        standard: ParsedStep,
    ) -> bool | None:
        if student.kind == "relation" and standard.kind == "relation":
            assert isinstance(student.value, Boolean)
            assert isinstance(standard.value, Boolean)
            return relations_equivalent(
                student.value, standard.value, self._symbol
            )

        if student.kind == "expression" and standard.kind == "expression":
            assert isinstance(student.value, Expr)
            assert isinstance(standard.value, Expr)
            return expressions_equivalent(student.value, standard.value)

        if student.kind == "limit" or standard.kind == "limit":
            return self._limit_pair(student, standard)

        if student.kind == "derivative" or standard.kind == "derivative":
            return self._derivative_pair(student, standard)

        if student.kind == "integral" or standard.kind == "integral":
            return self._integral_pair(student, standard)

        if student.kind == "matrix" and standard.kind == "matrix":
            assert isinstance(student.value, MatrixClaim)
            assert isinstance(standard.value, MatrixClaim)
            return matrices_equivalent(student.value, standard.value)

        return None

    def _limit_pair(
        self, student: ParsedStep, standard: ParsedStep
    ) -> bool | None:
        if student.kind == "limit" and standard.kind == "limit":
            assert isinstance(student.value, LimitClaim)
            assert isinstance(standard.value, LimitClaim)
            return limits_equivalent(student.value, standard.value)
        if student.kind == "limit" and standard.kind == "expression":
            assert isinstance(student.value, LimitClaim)
            assert isinstance(standard.value, Expr)
            return limits_equivalent(student.value, standard.value)
        if standard.kind == "limit" and student.kind == "expression":
            assert isinstance(standard.value, LimitClaim)
            assert isinstance(student.value, Expr)
            return limits_equivalent(standard.value, student.value)
        return None

    def _derivative_pair(
        self, student: ParsedStep, standard: ParsedStep
    ) -> bool | None:
        if student.kind == "derivative" and standard.kind == "derivative":
            assert isinstance(student.value, DerivativeClaim)
            assert isinstance(standard.value, DerivativeClaim)
            return derivatives_equivalent(student.value, standard.value)
        if student.kind == "derivative" and standard.kind == "expression":
            assert isinstance(student.value, DerivativeClaim)
            assert isinstance(standard.value, Expr)
            return derivatives_equivalent(student.value, standard.value)
        if standard.kind == "derivative" and student.kind == "expression":
            assert isinstance(standard.value, DerivativeClaim)
            assert isinstance(student.value, Expr)
            return derivatives_equivalent(standard.value, student.value)
        return None

    def _integral_pair(
        self, student: ParsedStep, standard: ParsedStep
    ) -> bool | None:
        if student.kind == "integral" and standard.kind == "integral":
            assert isinstance(student.value, IntegralClaim)
            assert isinstance(standard.value, IntegralClaim)
            return integrals_equivalent(student.value, standard.value)
        if student.kind == "integral" and standard.kind == "expression":
            assert isinstance(student.value, IntegralClaim)
            assert isinstance(standard.value, Expr)
            return integrals_equivalent(student.value, standard.value)
        if standard.kind == "integral" and student.kind == "expression":
            assert isinstance(standard.value, IntegralClaim)
            assert isinstance(student.value, Expr)
            return integrals_equivalent(standard.value, student.value)
        return None
