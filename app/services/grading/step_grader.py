"""Grade questions using rubric + validation artifacts."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import (
    GradingError,
    QuestionsNotFoundError,
    ValidationNotFoundError,
    ValidationStaleError,
)
from app.functions.question_names import (
    grading_filename,
    question_artifact_filename,
    validation_filename,
)
from app.functions.score_aggregate import aggregate_question_grade
from app.functions.validation_artifact import question_fingerprint
from app.models.grading import QuestionGrade
from app.models.question import Question
from app.models.validation import QuestionValidation, ValidationStatus
from app.services.grading.feedback_annotator import FeedbackAnnotator
from app.services.grading.rubric import RubricLoader
from app.services.grading.standard_comparer import (
    FIGURE_UNCOMPARED_REASON,
    StandardFinalComparer,
)

logger = logging.getLogger(__name__)


class StepGrader:
    def __init__(
        self,
        rubric_loader: RubricLoader,
        feedback_annotator: FeedbackAnnotator | None = None,
        standard_comparer: StandardFinalComparer | None = None,
        role_rubric_parts: Mapping[str, str] | None = None,
    ) -> None:
        self._rubrics = rubric_loader
        self._annotator = feedback_annotator
        self._standard_comparer = standard_comparer
        self._role_rubric_parts = dict(role_rubric_parts or {})

    def grade_question_dir(self, question_dir: Path) -> QuestionGrade:
        question_dir = Path(question_dir)
        question_path = question_dir / question_artifact_filename()
        validation_path = question_dir / validation_filename()
        if not question_path.is_file():
            raise QuestionsNotFoundError(question_dir)
        if not validation_path.is_file():
            raise ValidationNotFoundError(validation_path)

        try:
            question = Question.model_validate_json(
                question_path.read_text(encoding="utf-8")
            )
            validation = QuestionValidation.model_validate_json(
                validation_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise GradingError(question_dir.name, str(exc)) from exc
        if validation.question_fingerprint and (
            validation.question_fingerprint != question_fingerprint(question)
        ):
            raise ValidationStaleError(validation_path)

        rubric = self._rubrics.load(question.question_number)
        rubric_has_figure = any(c.id == "figure" for c in rubric.criteria)

        standard_status: ValidationStatus | None = None
        standard_reason = ""
        standard_step_results: dict[int, tuple[ValidationStatus, str]] | None = None
        part_statuses: dict[str, tuple] = {}
        step_overrides: dict[int, tuple[ValidationStatus, str]] = {}
        if self._standard_comparer is not None:
            compared = self._standard_comparer.compare(question)
            if compared is not None:
                standard_status, standard_reason = compared
            first_step = self._standard_comparer.compare_first_step(question)
            if first_step is not None:
                step_number, status, reason = first_step
                step_overrides[step_number] = (status, reason)
            standard_step_results = self._standard_comparer.compare_steps(question)
            part_statuses.update(
                self._standard_comparer.compare_milestones(question)
            )
            if rubric_has_figure:
                part_statuses["figure"] = self._standard_comparer.compare_figure(
                    question
                )
        elif rubric_has_figure:
            has_figure = any(
                step.role == "figure"
                or (step.symbolic is not None and step.symbolic.kind == "figure")
                for step in question.student_steps
            ) or bool(question.figure_refs)
            if has_figure:
                part_statuses["figure"] = (
                    ValidationStatus.UNCERTAIN,
                    FIGURE_UNCOMPARED_REASON,
                )
            else:
                part_statuses["figure"] = (
                    ValidationStatus.INVALID,
                    "no figure step",
                )

        grade = aggregate_question_grade(
            question_id=question.question_id,
            question_number=question.question_number,
            validation=validation,
            rubric=rubric,
            standard_final_status=standard_status,
            standard_final_reason=standard_reason,
            standard_step_results=standard_step_results,
            part_statuses=part_statuses,
            step_overrides=step_overrides,
            step_roles={step.step_number: step.role for step in question.student_steps},
            role_rubric_parts=self._role_rubric_parts,
        )
        if self._annotator is not None:
            grade = self._annotator.annotate(question, grade, validation)

        out = question_dir / grading_filename()
        try:
            original = question_path.read_text(encoding="utf-8")
            out.write_text(grade.model_dump_json(indent=2), encoding="utf-8")
            after = question_path.read_text(encoding="utf-8")
            if after != original:
                raise GradingError(
                    question.question_id,
                    "question.json was modified while writing grading.json",
                )
        except OSError as exc:
            raise GradingError(question.question_id, str(exc)) from exc

        logger.info(
            "Graded %s: %s/%s %s",
            question.question_id,
            grade.score,
            grade.maximum_score,
            grade.review_status.value,
        )
        return grade
