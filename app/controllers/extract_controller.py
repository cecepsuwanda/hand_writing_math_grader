from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.models.question import ExtractResult
from app.models.recognition import RecognizeResult
from app.services.questions.extractor import (
    QuestionExtractor,
    has_recognition_artifacts,
)


class ExtractController:
    def __init__(
        self,
        extractor: QuestionExtractor,
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
                from app.exceptions import RecognitionNotFoundError

                raise RecognitionNotFoundError(recognition_dir)
            self._recognize_runner()
        return self._extractor.extract_from_dir(recognition_dir, output_dir)
