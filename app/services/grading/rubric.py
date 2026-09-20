"""Load per-question rubrics from a standards directory."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from app.exceptions import RubricNotFoundError
from app.functions.question_names import question_dir_name
from app.models.grading import Rubric


class RubricLoader:
    def __init__(self, standard_dir: Path) -> None:
        self._standard_dir = Path(standard_dir)

    def load(self, question_number: int) -> Rubric:
        path = (
            self._standard_dir
            / "rubrics"
            / f"{question_dir_name(question_number)}.json"
        )
        if not path.is_file():
            raise RubricNotFoundError(path)
        try:
            return Rubric.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise RubricNotFoundError(path) from exc
