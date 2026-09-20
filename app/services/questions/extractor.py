"""Load recognition artifacts and write per-question extraction JSON."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import (
    EmptyExtractionError,
    InvalidRecognitionJsonError,
    RecognitionNotFoundError,
)
from app.functions.question_names import question_artifact_filename, question_dir_name
from app.models.question import ExtractResult, Question
from app.models.recognition import PageRecognition
from app.services.questions.segmenter import QuestionSegmenter

logger = logging.getLogger(__name__)

_PAGE_RECOGNITION_RE = re.compile(r"page_(\d+)_recognition\.json$", re.IGNORECASE)


class QuestionExtractor:
    def __init__(self, segmenter: QuestionSegmenter | None = None) -> None:
        self._segmenter = segmenter or QuestionSegmenter()

    def extract_from_dir(
        self,
        recognition_dir: Path,
        output_dir: Path,
    ) -> ExtractResult:
        pages = load_page_recognitions(recognition_dir)
        return self.extract_from_pages(pages, output_dir)

    def extract_from_pages(
        self,
        pages: list[PageRecognition],
        output_dir: Path,
    ) -> ExtractResult:
        questions = self._segmenter.segment(pages)
        if not questions:
            raise EmptyExtractionError()

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact_paths: list[Path] = []
        for question in questions:
            path = self._write_question(output_dir, question)
            artifact_paths.append(path)
            self._write_page_refs(output_dir, question)

        logger.info(
            "Extracted %s question(s) to %s",
            len(questions),
            output_dir,
        )
        return ExtractResult(
            questions=questions,
            output_dir=output_dir,
            artifact_paths=artifact_paths,
        )

    def _write_question(self, output_dir: Path, question: Question) -> Path:
        question_dir = output_dir / question_dir_name(question.question_number)
        question_dir.mkdir(parents=True, exist_ok=True)
        path = question_dir / question_artifact_filename()
        path.write_text(question.model_dump_json(indent=2), encoding="utf-8")
        return path

    def _write_page_refs(self, output_dir: Path, question: Question) -> None:
        question_dir = output_dir / question_dir_name(question.question_number)
        snapshot = {
            "question_id": question.question_id,
            "page_references": question.page_references,
        }
        path = question_dir / "recognition_pages.json"
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def load_page_recognitions(recognition_dir: Path) -> list[PageRecognition]:
    recognition_dir = Path(recognition_dir)
    if not recognition_dir.is_dir():
        raise RecognitionNotFoundError(recognition_dir)

    paths = sorted(recognition_dir.glob("page_*_recognition.json"))
    if not paths:
        raise RecognitionNotFoundError(recognition_dir)

    pages: list[PageRecognition] = []
    for path in paths:
        match = _PAGE_RECOGNITION_RE.search(path.name)
        page_number = int(match.group(1)) if match else 0
        try:
            pages.append(
                PageRecognition.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise InvalidRecognitionJsonError(page_number, str(exc)) from exc

    pages.sort(key=lambda page: page.page_number)
    return pages


def has_recognition_artifacts(recognition_dir: Path) -> bool:
    recognition_dir = Path(recognition_dir)
    return recognition_dir.is_dir() and any(
        recognition_dir.glob("page_*_recognition.json")
    )
