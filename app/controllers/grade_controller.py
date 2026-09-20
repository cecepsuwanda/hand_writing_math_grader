"""Orchestrate rubric grading for all questions in a directory."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import QuestionsNotFoundError
from app.functions.question_names import grading_filename, question_artifact_filename
from app.models.grading import GradeResult
from app.services.grading.step_grader import StepGrader

logger = logging.getLogger(__name__)


class GradeController:
    def __init__(self, grader: StepGrader, standard_dir: Path) -> None:
        self._grader = grader
        self._standard_dir = Path(standard_dir)

    def grade(self, questions_dir: Path) -> GradeResult:
        questions_dir = Path(questions_dir)
        question_paths = sorted(questions_dir.glob(f"*/{question_artifact_filename()}"))
        if not question_paths:
            raise QuestionsNotFoundError(questions_dir)

        grades = []
        artifact_paths = []
        for path in question_paths:
            grade = self._grader.grade_question_dir(path.parent)
            grades.append(grade)
            artifact_paths.append(path.parent / grading_filename())

        logger.info("Graded %s question(s) under %s", len(grades), questions_dir)
        return GradeResult(
            grades=grades,
            questions_dir=questions_dir,
            standard_dir=self._standard_dir,
            artifact_paths=artifact_paths,
        )
