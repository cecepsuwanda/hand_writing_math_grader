"""Optional LLM annotator: enriches feedback without changing scores."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import OllamaTimeoutError, OllamaUnavailableError
from app.functions.json_extract import extract_json_object
from app.models.grading import FeedbackAnnotation, QuestionGrade
from app.models.question import Question
from app.models.validation import QuestionValidation
from app.interfaces.llm_client import LlmClient

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "grading.txt"
PROMPT_VERSION = "grading-v1"


class FeedbackAnnotator:
    def __init__(
        self,
        client: LlmClient,
        model: str,
        prompt_path: Path | None = None,
    ) -> None:
        self._client = client
        self._model = model.strip()
        self._prompt_path = Path(prompt_path) if prompt_path else DEFAULT_PROMPT_PATH
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def annotate(
        self,
        question: Question,
        grade: QuestionGrade,
        validation: QuestionValidation | None = None,
    ) -> QuestionGrade:
        """Enrich feedback; part grades keep their deterministic text.

        ``validation`` supplies the validator's own reason so the prompt can
        tell it apart from the already-composed feedback. Without it the
        feedback text stands in for both, as before.
        """
        if not self._model:
            return grade

        steps_by_number = {s.step_number: s for s in question.student_steps}
        reasons = (
            {s.step_number: s.reason for s in validation.steps}
            if validation is not None
            else {}
        )
        new_steps = []
        for step_grade in grade.steps:
            # A rubric part is not a student step: no text to show the LLM, and
            # its ``part:<id>;`` feedback is already deterministic.
            if step_grade.part_id is not None:
                new_steps.append(step_grade)
                continue
            student_step = steps_by_number.get(step_grade.step_number)
            if student_step is None:
                new_steps.append(step_grade)
                continue
            if (
                student_step.symbolic is not None
                and (student_step.symbolic.repr or "").strip()
            ):
                step_text = student_step.symbolic.repr
            else:
                step_text = student_step.latex or student_step.raw_text
            annotated = self._annotate_one(
                validation_status=step_grade.validation_status.value,
                validation_reason=reasons.get(
                    step_grade.step_number, step_grade.feedback
                ),
                current_feedback=step_grade.feedback,
                step_text=step_text,
            )
            if annotated is None:
                new_steps.append(step_grade)
            else:
                new_steps.append(
                    step_grade.model_copy(
                        update={
                            "error_type": annotated.error_type,
                            "feedback": annotated.feedback
                            or step_grade.feedback,
                        }
                    )
                )

        final = grade.final_answer
        if final is not None:
            final_reason = final.feedback
            if validation is not None and validation.final_answer_status is not None:
                final_reason = (
                    validation.final_answer_status.reason or final.feedback
                )
            annotated = self._annotate_one(
                validation_status=final.validation_status.value,
                validation_reason=final_reason,
                current_feedback=final.feedback,
                step_text=question.student_final_answer,
            )
            if annotated is not None:
                final = final.model_copy(
                    update={
                        "error_type": annotated.error_type,
                        "feedback": annotated.feedback or final.feedback,
                    }
                )

        return grade.model_copy(update={"steps": new_steps, "final_answer": final})

    def _annotate_one(
        self,
        *,
        validation_status: str,
        validation_reason: str,
        current_feedback: str,
        step_text: str,
    ) -> FeedbackAnnotation | None:
        prompt = (
            self._template.replace("{{validation_status}}", validation_status)
            .replace("{{validation_reason}}", validation_reason)
            .replace("{{current_feedback}}", current_feedback)
            .replace("{{step_text}}", step_text or "(empty)")
        )
        try:
            raw = self._client.generate(prompt, self._model)
            payload = extract_json_object(raw)
            annotation = FeedbackAnnotation.model_validate(payload)
            if annotation.feedback:
                annotation = annotation.model_copy(
                    update={
                        "feedback": f"{annotation.feedback} (prompt={PROMPT_VERSION})"
                    }
                )
            return annotation
        except (
            OllamaUnavailableError,
            OllamaTimeoutError,
            ValueError,
            ValidationError,
        ) as exc:
            logger.warning("feedback annotator failed: %s", exc)
            return None
