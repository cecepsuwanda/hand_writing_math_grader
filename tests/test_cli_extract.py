from pathlib import Path

from app.cli import main
from app.models.recognition import PageRecognition, RecognizedQuestion, RecognizedStep
from tests.helpers import write_pdf


def test_cli_extract_from_existing_recognition(tmp_path: Path, capsys) -> None:
    pdf_path = write_pdf(tmp_path / "answer.pdf", 1)
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    page = PageRecognition(
        page_number=1,
        questions=[
            RecognizedQuestion(
                question_number=1,
                steps=[RecognizedStep(step_number=1, raw_text="x>0", latex="x>0")],
                final_answer="x>0",
            )
        ],
    )
    (recognition_dir / "page_001_recognition.json").write_text(
        page.model_dump_json(indent=2),
        encoding="utf-8",
    )
    output_dir = tmp_path / "questions"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "pdf:",
                "  dpi: 72",
                f"  output_dir: {(tmp_path / 'pages').as_posix()}",
                "ollama:",
                '  vision_model: "vision-test"',
                "recognition:",
                f"  output_dir: {recognition_dir.as_posix()}",
                "questions:",
                f"  output_dir: {output_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "extract",
            str(pdf_path),
            "--recognition-dir",
            str(recognition_dir),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "question_001" / "question.json").is_file()
    captured = capsys.readouterr()
    assert "Extracted 1 question(s)" in captured.out


def test_cli_extract_missing_recognition_without_model(
    tmp_path: Path,
    capsys,
) -> None:
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
                "questions:",
                f"  output_dir: {(tmp_path / 'questions').as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "extract",
            str(pdf_path),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Vision model is not configured" in captured.err
