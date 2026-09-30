"""Port for merging page recognition JSON into per-question artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.models.question import ExtractResult


@runtime_checkable
class QuestionExtractorPort(Protocol):
    def extract_from_dir(self, recognition_dir: Path, output_dir: Path) -> ExtractResult:
        """Read ``page_*_recognition.json`` and write ``question_NNN/question.json``."""
