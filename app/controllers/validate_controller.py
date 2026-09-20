"""Orchestrate SymPy validation and persist validation.json artifacts."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import QuestionsNotFoundError, ValidationWriteError
from app.functions.question_names import question_artifact_filename, validation_filename
from app.interfaces.validator import StepValidator
from app.models.question import Question
from app.models.validation import QuestionValidation, ValidateResult

logger = logging.getLogger(__name__)


class ValidateController:
    def __init__(self, validator: StepValidator) -> None:
        self._validator = validator

    def validate(self, questions_dir: Path) -> ValidateResult:
        questions_dir = Path(questions_dir)
        question_paths = sorted(questions_dir.glob(f"*/{question_artifact_filename()}"))
        if not question_paths:
            raise QuestionsNotFoundError(questions_dir)

        validations: list[QuestionValidation] = []
        artifact_paths: list[Path] = []
        for path in question_paths:
            question = self._load_question(path)
            original = path.read_text(encoding="utf-8")
            validation = self._validator.validate_question(question)
            artifact = self._write_validation(path.parent, validation)
            after = path.read_text(encoding="utf-8")
            if after != original:
                raise ValidationWriteError(
                    question.question_id,
                    "question.json was modified while writing validation.json",
                )
            validations.append(validation)
            artifact_paths.append(artifact)

        logger.info(
            "Wrote %s validation.json file(s) under %s",
            len(artifact_paths),
            questions_dir,
        )
        return ValidateResult(
            validations=validations,
            questions_dir=questions_dir,
            artifact_paths=artifact_paths,
        )

    def _load_question(self, path: Path) -> Question:
        try:
            return Question.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise ValidationWriteError(path.parent.name, str(exc)) from exc

    def _write_validation(
        self,
        question_dir: Path,
        validation: QuestionValidation,
    ) -> Path:
        path = question_dir / validation_filename()
        try:
            path.write_text(validation.model_dump_json(indent=2), encoding="utf-8")
        except OSError as exc:
            raise ValidationWriteError(validation.question_id, str(exc)) from exc
        return path
