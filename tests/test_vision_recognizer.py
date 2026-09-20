from pathlib import Path

import pytest

from app.exceptions import InvalidRecognitionJsonError, OllamaModelNotConfiguredError
from app.services.vision.recognizer import OllamaVisionRecognizer, PROMPT_VERSION


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[str, Path, str]] = []

    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        self.calls.append((prompt, image_path, model))
        return self.content


def test_recognizer_writes_artifact(tmp_path: Path) -> None:
    image = tmp_path / "page_001.png"
    image.write_bytes(b"png")
    out = tmp_path / "recognition"
    client = FakeClient(
        '{"page_number": 1, "questions": [{"question_number": 1, "steps": '
        '[{"step_number": 1, "raw_text": "x>0", "latex": "x>0"}], '
        '"final_answer": "x>0"}]}'
    )
    recognizer = OllamaVisionRecognizer(
        client=client,  # type: ignore[arg-type]
        model="vision-test",
        output_dir=out,
    )

    page = recognizer.recognize_page(image, 1)

    assert page.page_number == 1
    assert page.model == "vision-test"
    assert page.prompt_version == PROMPT_VERSION
    assert page.questions[0].final_answer == "x>0"
    artifact = out / "page_001_recognition.json"
    assert artifact.is_file()
    assert image.is_file()


def test_recognizer_invalid_json_keeps_image(tmp_path: Path) -> None:
    image = tmp_path / "page_001.png"
    image.write_bytes(b"png")
    out = tmp_path / "recognition"
    client = FakeClient("not json at all")
    recognizer = OllamaVisionRecognizer(
        client=client,  # type: ignore[arg-type]
        model="vision-test",
        output_dir=out,
    )

    with pytest.raises(InvalidRecognitionJsonError):
        recognizer.recognize_page(image, 1)

    assert image.is_file()
    assert not (out / "page_001_recognition.json").exists()


def test_recognizer_requires_model(tmp_path: Path) -> None:
    image = tmp_path / "page_001.png"
    image.write_bytes(b"png")
    recognizer = OllamaVisionRecognizer(
        client=FakeClient("{}"),  # type: ignore[arg-type]
        model="",
        output_dir=tmp_path / "recognition",
    )
    with pytest.raises(OllamaModelNotConfiguredError):
        recognizer.recognize_page(image, 1)
