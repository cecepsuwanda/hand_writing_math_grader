"""Read ``question_NNN/grading.json`` artifacts."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from app.functions.question_names import grading_filename
from app.models.grading import QuestionGrade


def grading_artifact_paths(questions_dir: Path) -> list[Path]:
    return sorted(Path(questions_dir).glob(f"*/{grading_filename()}"))


def load_question_grade(path: Path) -> QuestionGrade:
    """Parse one grading.json; ``ValueError`` if unreadable or invalid."""
    try:
        return QuestionGrade.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ValueError(f"invalid grading artifact {path}: {exc}") from exc


def load_question_grades(paths: list[Path]) -> list[QuestionGrade]:
    return [load_question_grade(path) for path in paths]
