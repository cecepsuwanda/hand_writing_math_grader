"""Orchestrate rubric grading for all questions in a directory."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import QuestionsNotFoundError, RubricNotFoundError
from app.functions.question_names import grading_filename, question_artifact_filename
from app.interfaces.grader import QuestionGrader
from app.models.grading import GradeResult

logger = logging.getLogger(__name__)


class GradeController:
    def __init__(self, grader: QuestionGrader, standard_dir: Path) -> None:
        self._grader = grader
        self._standard_dir = Path(standard_dir)

    def grade(self, questions_dir: Path) -> GradeResult:
        """A question without a (valid) rubric is skipped with a warning; its old
        ``grading.json`` is removed so the report shows it as ungraded."""
        questions_dir = Path(questions_dir)
        question_paths = sorted(questions_dir.glob(f"*/{question_artifact_filename()}"))
        if not question_paths:
            raise QuestionsNotFoundError(questions_dir)

        grades = []
        artifact_paths = []
        skipped: list[str] = []
        first_error: RubricNotFoundError | None = None
        for path in question_paths:
            try:
                grade = self._grader.grade_question_dir(path.parent)
            except RubricNotFoundError as exc:
                first_error = first_error or exc
                skipped.append(path.parent.name)
                (path.parent / grading_filename()).unlink(missing_ok=True)
                logger.warning(f"{path.parent.name} tidak dinilai: {exc}")
                continue
            grades.append(grade)
            artifact_paths.append(path.parent / grading_filename())

        if not grades and first_error is not None:
            raise first_error
        logger.info("Graded %s question(s) under %s", len(grades), questions_dir)
        return GradeResult(
            grades=grades,
            questions_dir=questions_dir,
            standard_dir=self._standard_dir,
            artifact_paths=artifact_paths,
            skipped=skipped,
        )
