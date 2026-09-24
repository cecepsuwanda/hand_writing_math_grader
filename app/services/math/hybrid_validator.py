"""SymPy-first validator with LLM fallback for uncertain steps only."""

from __future__ import annotations

import logging

from app.interfaces.validator import StepValidator
from app.models.question import Question, StudentStep
from app.models.validation import (
    QuestionValidation,
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
    ) -> None:
        self._sympy = sympy_validator
        self._llm = llm_judge

    def validate_question(self, question: Question) -> QuestionValidation:
        base = self._sympy.validate_question(question)
        steps_by_number = {
            step.step_number: step
            for step in sorted(question.student_steps, key=lambda s: s.step_number)
        }
        ordered = sorted(question.student_steps, key=lambda s: s.step_number)

        refined_steps: list[StepValidation] = []
        for index, step_result in enumerate(base.steps):
            if step_result.status != ValidationStatus.UNCERTAIN:
                refined_steps.append(step_result)
                continue

            current = steps_by_number.get(step_result.step_number)
            previous = ordered[index - 1] if index > 0 else None
            judged = self._llm.judge_transition(
                step_number=step_result.step_number,
                previous=previous,
                current=current,
                extra_context=f"SymPy reason: {step_result.reason}",
            )
            refined_steps.append(judged)
            logger.info(
                "LLM fallback question=%s step=%s status=%s",
                question.question_id,
                step_result.step_number,
                judged.status.value,
            )

        final_status = base.final_answer_status
        if (
            final_status is not None
            and final_status.status == ValidationStatus.UNCERTAIN
        ):
            last_step: StudentStep | None = ordered[-1] if ordered else None
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
                last_step=last_step,
                final_answer=final_text,
            )

        return QuestionValidation(
            question_number=base.question_number,
            question_id=base.question_id,
            steps=refined_steps,
            final_answer_status=final_status,
        )
