"""Orchestrate SymPy validation and persist validation.json artifacts."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import QuestionsNotFoundError, ValidationWriteError
from app.functions.artifact_guard import changed_files, snapshot_files
from app.functions.validation_artifact import (
    load_question_artifact,
    question_artifact_paths,
    question_fingerprint,
    write_validation_artifact,
)
from app.interfaces.validator import StepValidator
from app.models.question import Question
from app.models.validation import QuestionValidation, ValidateResult

logger = logging.getLogger(__name__)


class ValidateController:
    def __init__(self, validator: StepValidator) -> None:
        self._validator = validator

    def validate(self, questions_dir: Path) -> ValidateResult:
        questions_dir = Path(questions_dir)
        question_paths = question_artifact_paths(questions_dir)
        if not question_paths:
            raise QuestionsNotFoundError(questions_dir)

        validations: list[QuestionValidation] = []
        artifact_paths: list[Path] = []
        for path in question_paths:
            question = self._load_question(path)
            snapshot = snapshot_files([path])
            validation = self._validator.validate_question(question).model_copy(
                update={"question_fingerprint": question_fingerprint(question)}
            )
            artifact = self._write_validation(path.parent, validation)
            if changed_files(snapshot):
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

    @staticmethod
    def _load_question(path: Path) -> Question:
        try:
            return load_question_artifact(path)
        except ValueError as exc:
            raise ValidationWriteError(path.parent.name, str(exc)) from exc

    @staticmethod
    def _write_validation(question_dir: Path, validation: QuestionValidation) -> Path:
        try:
            return write_validation_artifact(question_dir, validation)
        except OSError as exc:
            raise ValidationWriteError(validation.question_id, str(exc)) from exc
