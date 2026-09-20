"""Tests for recognition path consistency guard."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.controllers.recognize_controller import RecognizeController
from app.exceptions import RecognitionPathMismatchError
from app.models.page import Page
from app.models.recognition import PageRecognition


def test_recognize_pages_rejects_output_dir_mismatch(tmp_path: Path) -> None:
    recognizer = MagicMock()
    recognizer.output_dir = tmp_path / "wrong"
    recognizer.recognize_page.return_value = PageRecognition(
        page_number=1, questions=[]
    )
    controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
    pages = [Page(page_number=1, image="page_001.png", width=10, height=10)]

    with pytest.raises(RecognitionPathMismatchError):
        controller.recognize_pages(pages, tmp_path / "pages", tmp_path / "recognition")


def test_recognize_pages_allows_matching_output_dir(tmp_path: Path) -> None:
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    recognizer = MagicMock()
    recognizer.output_dir = recognition_dir
    recognizer.recognize_page.return_value = PageRecognition(
        page_number=1, questions=[]
    )
    controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page_001.png").write_bytes(b"x")
    pages = [Page(page_number=1, image="page_001.png", width=10, height=10)]

    result = controller.recognize_pages(pages, pages_dir, recognition_dir)

    assert result.output_dir == recognition_dir
    assert len(result.artifact_paths) == 1
