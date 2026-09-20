"""Grade questions using rubric + validation artifacts."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import (
    GradingError,
    QuestionsNotFoundError,
    ValidationNotFoundError,
)
from app.functions.question_names import (
    grading_filename,
    question_artifact_filename,
    validation_filename,
)
from app.functions.score_aggregate import aggregate_question_grade
from app.models.grading import QuestionGrade
from app.models.question import Question
from app.models.validation import QuestionValidation
from app.services.grading.feedback_annotator import FeedbackAnnotator
from app.services.grading.rubric import RubricLoader

logger = logging.getLogger(__name__)


class StepGrader:
    def __init__(
        self,
        rubric_loader: RubricLoader,
        feedback_annotator: FeedbackAnnotator | None = None,
    ) -> None:
        self._rubrics = rubric_loader
        self._annotator = feedback_annotator

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

        rubric = self._rubrics.load(question.question_number)
        grade = aggregate_question_grade(
            question_id=question.question_id,
            question_number=question.question_number,
            validation=validation,
            rubric=rubric,
        )
        if self._annotator is not None:
            grade = self._annotator.annotate(question, grade)

        out = question_dir / grading_filename()
        try:
            # Ensure question.json unchanged
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
