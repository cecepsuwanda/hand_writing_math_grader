"""Merge recognition JSON into per-question artifacts (recognize first if missing)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.exceptions import RecognitionNotFoundError
from app.functions.recognition_artifact import has_recognition_artifacts
from app.interfaces.extractor import QuestionExtractorPort
from app.models.question import ExtractResult
from app.models.recognition import RecognizeResult


class ExtractController:
    def __init__(
        self,
        extractor: QuestionExtractorPort,
        recognize_runner: Callable[[], RecognizeResult] | None = None,
    ) -> None:
        self._extractor = extractor
        self._recognize_runner = recognize_runner

    def extract(
        self,
        recognition_dir: Path,
        output_dir: Path,
        *,
        force_recognize: bool = False,
    ) -> ExtractResult:
        if force_recognize or not has_recognition_artifacts(recognition_dir):
            if self._recognize_runner is None:
                raise RecognitionNotFoundError(recognition_dir)
            self._recognize_runner()
        return self._extractor.extract_from_dir(recognition_dir, output_dir)
