from pathlib import Path
from unittest.mock import MagicMock

from app.cli import main
from app.models.page import Page
from app.models.recognition import PageRecognition
from tests.helpers import write_pdf


def test_cli_recognize_writes_json_and_exits_zero(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pdf_path = write_pdf(tmp_path / "answer.pdf", 1)
    pages_dir = tmp_path / "pages"
    recognition_dir = tmp_path / "recognition"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "pdf:",
                "  dpi: 72",
                f"  output_dir: {pages_dir.as_posix()}",
                "ollama:",
                '  base_url: "http://localhost:11434"',
                '  vision_model: "vision-test"',
                "  timeout_seconds: 5",
                "  max_retries: 0",
                "recognition:",
                f"  output_dir: {recognition_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    fake_page = Page(page_number=1, image="page_001.png", width=10, height=10)
    fake_recognition = PageRecognition(
        page_number=1,
        questions=[],
        prompt_version="recognition-v1",
        model="vision-test",
    )

    class FakeRenderer:
        def render(self, pdf_path: Path, output_dir: Path, dpi: int) -> list[Page]:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "page_001.png").write_bytes(b"png")
            return [fake_page]

    class FakeRecognizer:
        def recognize_page(self, image_path: Path, page_number: int) -> PageRecognition:
            recognition_dir.mkdir(parents=True, exist_ok=True)
            path = recognition_dir / "page_001_recognition.json"
            path.write_text(fake_recognition.model_dump_json(indent=2), encoding="utf-8")
            return fake_recognition

    monkeypatch.setattr("app.cli.PyMuPdfRenderer", FakeRenderer)
    monkeypatch.setattr("app.cli.OllamaClient", MagicMock)
    monkeypatch.setattr(
        "app.cli.OllamaVisionRecognizer",
        lambda **kwargs: FakeRecognizer(),
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "recognize",
            str(pdf_path),
            "--pages-dir",
            str(pages_dir),
            "--output",
            str(recognition_dir),
            "--dpi",
            "72",
        ]
    )

    assert exit_code == 0
    assert (pages_dir / "page_001.png").is_file()
    assert (recognition_dir / "page_001_recognition.json").is_file()
    captured = capsys.readouterr()
    assert "Recognized 1 page(s)" in captured.out


def test_cli_recognize_missing_model_exits_nonzero(tmp_path: Path, capsys) -> None:
    pdf_path = write_pdf(tmp_path / "answer.pdf", 1)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "pdf:",
                "  dpi: 72",
                f"  output_dir: {(tmp_path / 'pages').as_posix()}",
                "ollama:",
                '  vision_model: ""',
                "recognition:",
                f"  output_dir: {(tmp_path / 'recognition').as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "recognize",
            str(pdf_path),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Vision model is not configured" in captured.err
