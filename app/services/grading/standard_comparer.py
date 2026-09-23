"""Compare student final answer to standard solution via SymPy equivalence."""

from __future__ import annotations

import logging
from pathlib import Path

from sympy import Expr, Symbol
from sympy.logic.boolalg import Boolean

from app.exceptions import MathParseError
from app.functions.kunci_ingest import load_exam_schema
from app.functions.standard_extract import (
    schema_question,
    standard_final_text,
    standard_solution_path,
    standard_step_texts,
)
from app.models.exam_schema import ExamSchema
from app.models.question import Question, StudentStep
from app.models.validation import ValidationStatus
from app.services.math.equivalence import (
    derivatives_equivalent,
    expressions_equivalent,
    integrals_equivalent,
    limits_equivalent,
    matrices_equivalent,
    relations_equivalent,
    set_relation_equivalent,
    try_set_form_equivalence,
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
    """Compare student answers to exam_schema symbolic (fallback solutions/*.tex)."""

    def __init__(
        self,
        standard_dir: Path,
        exam_schema: ExamSchema | None = None,
        symbol: Symbol | None = None,
    ) -> None:
        self._standard_dir = Path(standard_dir)
        self._schema = (
            exam_schema
            if exam_schema is not None
            else load_exam_schema(self._standard_dir)
        )
        self._symbol = symbol or default_symbol()

    def expected_step_count(self, question_number: int) -> int | None:
        """Return standard step count for scoring incomplete solutions, or None."""
        schema_q = schema_question(self._schema, question_number)
        path = standard_solution_path(self._standard_dir, question_number)
        tex: str | None = None
        if path.is_file():
            try:
                tex = path.read_text(encoding="utf-8")
            except OSError:
                tex = None
        texts = standard_step_texts(schema_q, tex)
        return len(texts) if texts else None

    def compare(
        self,
        question: Question,
    ) -> tuple[ValidationStatus, str] | None:
        """Return (status, reason), or None if no schema question and no .tex."""
        schema_q = schema_question(self._schema, question.question_number)
        path = standard_solution_path(
            self._standard_dir, question.question_number
        )
        tex: str | None = None
        if path.is_file():
            try:
                tex = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read standard solution %s: %s", path, exc)
                if schema_q is None:
                    return (
                        ValidationStatus.UNCERTAIN,
                        f"could not read standard solution: {path}",
                    )

        if schema_q is None and tex is None:
            return None

        standard_text = standard_final_text(schema_q, tex)
        if not standard_text:
            return (
                ValidationStatus.UNCERTAIN,
                "no standard final answer in schema or TeX",
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

        Returns None if neither schema question nor solution file exists.
        Student steps beyond the standard step count are omitted.
        """
        schema_q = schema_question(self._schema, question.question_number)
        path = standard_solution_path(
            self._standard_dir, question.question_number
        )
        tex: str | None = None
        if path.is_file():
            try:
                tex = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read standard solution %s: %s", path, exc)
                if schema_q is None:
                    steps = sorted(
                        question.student_steps, key=lambda s: s.step_number
                    )
                    return {
                        step.step_number: (
                            ValidationStatus.UNCERTAIN,
                            f"could not read standard solution: {path}",
                        )
                        for step in steps
                    }

        if schema_q is None and tex is None:
            return None

        standard_texts = standard_step_texts(schema_q, tex)
        if not standard_texts:
            return {}

        student_steps = sorted(question.student_steps, key=lambda s: s.step_number)
        results: dict[int, tuple[ValidationStatus, str]] = {}
        for index, step in enumerate(student_steps):
            if index >= len(standard_texts):
                results[step.step_number] = (
                    ValidationStatus.INVALID,
                    "no matching standard step",
                )
                continue
            results[step.step_number] = self._compare_step_pair(
                step, standard_texts[index]
            )
        return results

    def _compare_step_pair(
        self,
        step: StudentStep,
        standard_text: str,
    ) -> tuple[ValidationStatus, str]:
        if step.symbolic is not None and step.symbolic.kind == "figure":
            return (
                ValidationStatus.UNCERTAIN,
                "figure step skipped for standard align",
            )
        student_text = ""
        if step.symbolic is not None and (step.symbolic.repr or "").strip():
            student_text = step.symbolic.repr.strip()
        if not student_text:
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
        if (
            question.student_final_symbolic is not None
            and (question.student_final_symbolic.repr or "").strip()
        ):
            return question.student_final_symbolic.repr.strip()
        final = (question.student_final_answer or "").strip()
        if final:
            return final
        if not question.student_steps:
            return ""
        last = max(question.student_steps, key=lambda s: s.step_number)
        if last.symbolic is not None and (last.symbolic.repr or "").strip():
            return last.symbolic.repr.strip()
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

        applicable, set_result = try_set_form_equivalence(
            student.kind,
            student.value,
            standard.kind,
            standard.value,
            self._symbol,
        )
        if applicable:
            return set_result

        if student.kind == "expression" and standard.kind == "expression":
            assert isinstance(student.value, Expr)
            assert isinstance(standard.value, Expr)
            return expressions_equivalent(student.value, standard.value)

        # Interval / set expression ↔ relation (HP forms).
        if student.kind == "expression" and standard.kind == "relation":
            assert isinstance(standard.value, Boolean)
            return set_relation_equivalent(
                student.value, standard.value, self._symbol
            )
        if student.kind == "relation" and standard.kind == "expression":
            assert isinstance(student.value, Boolean)
            return set_relation_equivalent(
                standard.value, student.value, self._symbol
            )

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
