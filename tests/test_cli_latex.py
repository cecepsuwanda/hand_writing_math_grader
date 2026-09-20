from pathlib import Path

from app.cli import main
from app.models.question import Question, StudentStep


def test_cli_latex_writes_student_tex(tmp_path: Path, capsys) -> None:
    questions_dir = tmp_path / "questions"
    question_dir = questions_dir / "question_001"
    question_dir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="2x=10", latex="2x = 10"),
        ],
        student_final_answer="x = 5",
    )
    (question_dir / "question.json").write_text(
        question.model_dump_json(indent=2),
        encoding="utf-8",
    )
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
                f"  output_dir: {(tmp_path / 'recognition').as_posix()}",
                "questions:",
                f"  output_dir: {questions_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "latex",
            "--questions-dir",
            str(questions_dir),
        ]
    )

    assert exit_code == 0
    assert (question_dir / "student.tex").is_file()
    captured = capsys.readouterr()
    assert "Built 1 student.tex" in captured.out


def test_cli_latex_missing_questions_exits_nonzero(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    empty_dir = tmp_path / "questions"
    empty_dir.mkdir()
    config_path.write_text(
        "\n".join(
            [
                "questions:",
                f"  output_dir: {empty_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["--config", str(config_path), "latex"])

    assert exit_code == 1
    assert "No question.json artifacts found" in capsys.readouterr().err
