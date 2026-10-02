"""SymPy-first validator with LLM fallback for uncertain steps only."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from app.functions.step_references import (
    final_reference_index,
    reference_indices,
    step_checks_for,
)
from app.interfaces.validator import StepValidator
from app.models.question import Question, StudentStep
from app.models.validation import (
    QuestionValidation,
    StepCheck,
    StepValidation,
    ValidationStatus,
)
from app.services.math.llm_judge import LlmStepJudge

logger = logging.getLogger(__name__)


class HybridStepValidator(StepValidator):
    def __init__(
        self,
        sympy_validator: StepValidator,
        llm_judge: LlmStepJudge,
        step_checks: Mapping[str, StepCheck] | None = None,
    ) -> None:
        self._sympy = sympy_validator
        self._llm = llm_judge
        self._step_checks = dict(step_checks or {})

    def validate_question(self, question: Question) -> QuestionValidation:
        base = self._sympy.validate_question(question)
        ordered = sorted(question.student_steps, key=lambda s: s.step_number)
        checks = step_checks_for([step.role for step in ordered], self._step_checks)
        references = reference_indices(checks)
        index_by_number = {step.step_number: i for i, step in enumerate(ordered)}

        refined_steps: list[StepValidation] = []
        for step_result in base.steps:
            if step_result.status != ValidationStatus.UNCERTAIN:
                refined_steps.append(step_result)
                continue

            index = index_by_number.get(step_result.step_number)
            current = ordered[index] if index is not None else None
            reference = self._step_at(ordered, references[index] if index is not None else None)
            check = checks[index] if index is not None else StepCheck.TRANSITION
            judged = self._llm.judge_transition(
                step_number=step_result.step_number,
                previous=reference,
                current=current,
                extra_context=(
                    f"Check kind: {check.value}\nSymPy reason: {step_result.reason}"
                ),
            )
            refined_steps.append(judged)
            logger.info(
                "LLM fallback question=%s step=%s check=%s status=%s",
                question.question_id,
                step_result.step_number,
                check.value,
                judged.status.value,
            )

        final_status = base.final_answer_status
        if (
            final_status is not None
            and final_status.status == ValidationStatus.UNCERTAIN
        ):
            # Prefer symbolic.repr (same source SymPy used) over raw_text.
            final_text = ""
            if (
                question.student_final_symbolic is not None
                and (question.student_final_symbolic.repr or "").strip()
            ):
                final_text = question.student_final_symbolic.repr.strip()
            else:
                final_text = (question.student_final_answer or "").strip()
            final_status = self._llm.judge_final_answer(
                step_number=final_status.step_number,
                last_step=self._step_at(ordered, final_reference_index(checks)),
                final_answer=final_text,
            )

        return QuestionValidation(
            question_number=base.question_number,
            question_id=base.question_id,
            steps=refined_steps,
            final_answer_status=final_status,
        )

    def _step_at(self, ordered: list[StudentStep], index: int | None) -> StudentStep | None:
        return ordered[index] if index is not None else None
