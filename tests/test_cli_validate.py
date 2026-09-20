from pathlib import Path

from app.cli import main
from app.controllers.validate_controller import ValidateController
from app.models.question import Question, StudentStep
from app.services.math.sympy_validator import SymPyStepValidator


def test_validate_controller_writes_json_without_mutating_question(
    tmp_path: Path,
) -> None:
    qdir = tmp_path / "question_001"
    qdir.mkdir()
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="keep", latex="2x+5=15"),
            StudentStep(step_number=2, raw_text="keep", latex="2x=10"),
        ],
        student_final_answer="x=5",
    )
    qpath = qdir / "question.json"
    original = question.model_dump_json(indent=2)
    qpath.write_text(original, encoding="utf-8")

    result = ValidateController(SymPyStepValidator()).validate(tmp_path)

    assert (qdir / "validation.json").is_file()
    assert result.artifact_paths[0] == qdir / "validation.json"
    assert qpath.read_text(encoding="utf-8") == original
    assert "keep" in qpath.read_text(encoding="utf-8")


def test_cli_validate(tmp_path: Path, capsys) -> None:
    questions_dir = tmp_path / "questions"
    qdir = questions_dir / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="x<4"),
        ],
        student_final_answer="x<4",
    )
    (qdir / "question.json").write_text(
        question.model_dump_json(indent=2), encoding="utf-8"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"questions:\n  output_dir: {questions_dir.as_posix()}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "validate",
            "--questions-dir",
            str(questions_dir),
        ]
    )

    assert exit_code == 0
    assert (qdir / "validation.json").is_file()
    assert "Validated 1 question(s)" in capsys.readouterr().out


def test_cli_validate_with_reasoning_model_uses_hybrid(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    questions_dir = tmp_path / "questions"
    qdir = questions_dir / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="unparseable prose", latex=""),
        ],
    )
    (qdir / "question.json").write_text(
        question.model_dump_json(indent=2), encoding="utf-8"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "ollama:",
                '  base_url: "http://localhost:11434"',
                '  vision_model: "vision-test"',
                '  reasoning_model: "reason-test"',
                "  max_retries: 0",
                "questions:",
                f"  output_dir: {questions_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def generate(self, prompt: str, model: str) -> str:
            return (
                '{"status":"uncertain","reason":"still unclear","confidence":0.2}'
            )

    monkeypatch.setattr("app.cli.OllamaClient", lambda **kwargs: FakeClient())

    exit_code = main(
        [
            "--config",
            str(config_path),
            "validate",
            "--questions-dir",
            str(questions_dir),
        ]
    )

    assert exit_code == 0
    payload = (qdir / "validation.json").read_text(encoding="utf-8")
    assert '"method": "llm"' in payload
    assert '"status": "uncertain"' in payload
    assert "Validated 1 question(s)" in capsys.readouterr().out
