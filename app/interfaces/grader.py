"""Port for grading one question folder (question.json + validation.json)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.models.grading import QuestionGrade


@runtime_checkable
class QuestionGrader(Protocol):
    def grade_question_dir(self, question_dir: Path) -> QuestionGrade:
        """Grade one ``question_NNN`` folder and persist ``grading.json``."""
