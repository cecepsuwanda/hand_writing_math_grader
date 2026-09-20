"""SymPy-first step validator (no LLM)."""

from __future__ import annotations

import logging

from sympy import Symbol
from sympy.core.relational import Relational

from app.exceptions import MathParseError
from app.interfaces.validator import StepValidator
from app.models.question import Question, StudentStep
from app.models.validation import (
    QuestionValidation,
    StepValidation,
    ValidationMethod,
    ValidationStatus,
)
from app.services.math.equivalence import relations_equivalent
from app.services.math.parser import default_symbol, parse_relation

logger = logging.getLogger(__name__)


class SymPyStepValidator(StepValidator):
    def __init__(self, symbol: Symbol | None = None) -> None:
        self._symbol = symbol or default_symbol()

    def validate_question(self, question: Question) -> QuestionValidation:
        steps = sorted(question.student_steps, key=lambda s: s.step_number)
        parsed: list[Relational | None] = []
        step_results: list[StepValidation] = []

        for index, step in enumerate(steps):
            relation = self._try_parse(step)
            parsed.append(relation)
            if index == 0:
                step_results.append(self._validate_first(step, relation))
            else:
                step_results.append(
                    self._validate_transition(
                        step=step,
                        previous=parsed[index - 1],
                        current=relation,
                    )
                )

        final_status = None
        if (question.student_final_answer or "").strip() and steps:
            final_status = self._validate_final_answer(
                question.student_final_answer,
                parsed[-1],
                last_step_number=steps[-1].step_number,
            )

        result = QuestionValidation(
            question_number=question.question_number,
            question_id=question.question_id,
            steps=step_results,
            final_answer_status=final_status,
        )
        logger.info(
            "Validated %s: %s",
            question.question_id,
            [s.status.value for s in step_results],
        )
        return result

    def _step_expression(self, step: StudentStep) -> str:
        latex = (step.latex or "").strip()
        if latex:
            return latex
        return (step.raw_text or "").strip()

    def _try_parse(self, step: StudentStep) -> Relational | None:
        expression = self._step_expression(step)
        if not expression:
            return None
        try:
            return parse_relation(expression, self._symbol)
        except MathParseError:
            return None

    def _validate_first(
        self,
        step: StudentStep,
        relation: Relational | None,
    ) -> StepValidation:
        if relation is None:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="could not parse first step",
            )
        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.VALID,
            method=ValidationMethod.PARSE,
            reason="first step parsed successfully",
        )

    def _validate_transition(
        self,
        step: StudentStep,
        previous: Relational | None,
        current: Relational | None,
    ) -> StepValidation:
        if previous is None or current is None:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="could not parse step for SymPy comparison",
            )
        equivalent = relations_equivalent(previous, current, self._symbol)
        if equivalent is True:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.VALID,
                method=ValidationMethod.SYMPY,
                reason="solution sets are equivalent",
            )
        if equivalent is False:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.INVALID,
                method=ValidationMethod.SYMPY,
                reason="solution sets differ",
            )
        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.SYMPY,
            reason="SymPy could not decide equivalence",
        )

    def _validate_final_answer(
        self,
        final_answer: str,
        last_relation: Relational | None,
        last_step_number: int,
    ) -> StepValidation:
        try:
            final_rel = parse_relation(final_answer, self._symbol)
        except MathParseError:
            return StepValidation(
                step_number=last_step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="could not parse final answer",
            )
        if last_relation is None:
            return StepValidation(
                step_number=last_step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="last step not parseable for final-answer check",
            )
        equivalent = relations_equivalent(last_relation, final_rel, self._symbol)
        if equivalent is True:
            status = ValidationStatus.VALID
            reason = "final answer matches last step solution set"
        elif equivalent is False:
            status = ValidationStatus.INVALID
            reason = "final answer solution set differs from last step"
        else:
            status = ValidationStatus.UNCERTAIN
            reason = "SymPy could not compare final answer"
        return StepValidation(
            step_number=last_step_number,
            status=status,
            method=ValidationMethod.SYMPY,
            reason=reason,
        )
