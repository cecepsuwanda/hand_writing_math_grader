import json
from pathlib import Path

import pytest

from app.exceptions import EmptyExtractionError, RecognitionNotFoundError
from app.models.recognition import PageRecognition, RecognizedQuestion, RecognizedStep
from app.services.questions.extractor import QuestionExtractor


def _write_recognition(path: Path, page: PageRecognition) -> None:
    path.write_text(page.model_dump_json(indent=2), encoding="utf-8")


def test_extractor_writes_question_json(tmp_path: Path) -> None:
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    _write_recognition(
        recognition_dir / "page_001_recognition.json",
        PageRecognition(
            page_number=1,
            questions=[
                RecognizedQuestion(
                    question_number=1,
                    steps=[
                        RecognizedStep(step_number=1, raw_text="2x<8", latex="2x<8"),
                    ],
                    final_answer="x<4",
                )
            ],
            prompt_version="recognition-v1",
            model="test",
        ),
    )
    output_dir = tmp_path / "questions"

    result = QuestionExtractor().extract_from_dir(recognition_dir, output_dir)

    assert len(result.questions) == 1
    artifact = output_dir / "question_001" / "question.json"
    assert artifact.is_file()
    assert (output_dir / "question_001" / "recognition_pages.json").is_file()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["student_final_answer"] == "x<4"
    assert payload["question_id"] == "question_001"
    assert result.artifact_paths[0] == artifact


def test_extractor_missing_recognition_dir(tmp_path: Path) -> None:
    with pytest.raises(RecognitionNotFoundError):
        QuestionExtractor().extract_from_dir(tmp_path / "missing", tmp_path / "out")


def test_extractor_empty_questions(tmp_path: Path) -> None:
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    _write_recognition(
        recognition_dir / "page_001_recognition.json",
        PageRecognition(page_number=1, questions=[]),
    )
    with pytest.raises(EmptyExtractionError):
        QuestionExtractor().extract_from_dir(recognition_dir, tmp_path / "out")
