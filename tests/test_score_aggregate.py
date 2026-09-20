"""Unit and CLI tests for Phase 7 rubric grading."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli import main
from app.controllers.grade_controller import GradeController
from app.exceptions import ValidationNotFoundError
from app.functions.score_aggregate import aggregate_question_grade
from app.models.grading import (
    ReviewStatus,
    Rubric,
    RubricCriterion,
)
from app.models.question import Question, StudentStep
from app.models.validation import (
    QuestionValidation,
    StepValidation,
    ValidationMethod,
    ValidationStatus,
)
from app.services.grading.rubric import RubricLoader
from app.services.grading.step_grader import StepGrader


def _sample_rubric() -> Rubric:
    return Rubric(
        question=1,
        maximum_score=10,
        criteria=[
            RubricCriterion(id="setup", points=2),
            RubricCriterion(id="transformation", points=4),
            RubricCriterion(id="calculation", points=2),
            RubricCriterion(id="final_answer", points=2),
        ],
    )


def _step(n: int, status: ValidationStatus, reason: str = "") -> StepValidation:
    return StepValidation(
        step_number=n,
        status=status,
        method=ValidationMethod.SYMPY,
        reason=reason or status.value,
    )


def test_aggregate_full_credit() -> None:
    validation = QuestionValidation(
        question_number=1,
        question_id="question_001",
        steps=[
            _step(1, ValidationStatus.VALID),
            _step(2, ValidationStatus.VALID),
            _step(3, ValidationStatus.VALID),
            _step(4, ValidationStatus.VALID),
        ],
        final_answer_status=_step(0, ValidationStatus.VALID),
    )
    grade = aggregate_question_grade(
        question_id="question_001",
        question_number=1,
        validation=validation,
        rubric=_sample_rubric(),
    )
    assert grade.score == pytest.approx(10.0)
    assert grade.maximum_score == 10
    assert grade.review_status == ReviewStatus.AUTO_ACCEPT
    assert all(s.score == pytest.approx(2.0) for s in grade.steps)
    assert grade.final_answer is not None
    assert grade.final_answer.score == pytest.approx(2.0)


def test_aggregate_partial_credit_not_zero_total() -> None:
    # One middle step invalid + final invalid; others valid → mid-range score
    validation = QuestionValidation(
        question_number=1,
        question_id="question_001",
        steps=[
            _step(1, ValidationStatus.VALID),
            _step(2, ValidationStatus.INVALID, "algebra error"),
            _step(3, ValidationStatus.VALID),
            _step(4, ValidationStatus.VALID),
        ],
        final_answer_status=_step(0, ValidationStatus.INVALID, "wrong answer"),
    )
    grade = aggregate_question_grade(
        question_id="question_001",
        question_number=1,
        validation=validation,
        rubric=_sample_rubric(),
    )
    # Steps: 2 + 0 + 2 + 2 = 6; final 0 → 6 (not wiped to 0)
    assert grade.score == pytest.approx(6.0)
    assert 0 < grade.score < grade.maximum_score
    assert grade.review_status == ReviewStatus.AUTO_ACCEPT
    assert grade.steps[2].error_type.value == "carry_forward"


def test_aggregate_uncertain_requires_review() -> None:
    validation = QuestionValidation(
        question_number=1,
        question_id="question_001",
        steps=[
            _step(1, ValidationStatus.VALID),
            _step(2, ValidationStatus.UNCERTAIN, "ambiguous"),
            _step(3, ValidationStatus.VALID),
            _step(4, ValidationStatus.VALID),
        ],
        final_answer_status=_step(0, ValidationStatus.VALID),
    )
    grade = aggregate_question_grade(
        question_id="question_001",
        question_number=1,
        validation=validation,
        rubric=_sample_rubric(),
    )
    # Steps: 2 + 1 + 2 + 2 = 7; final 2 → 9
    assert grade.score == pytest.approx(9.0)
    assert grade.review_status == ReviewStatus.REVIEW_REQUIRED
    assert grade.steps[1].status.value == "review"


def test_step_grader_writes_grading_json_without_mutating_question(
    tmp_path: Path,
) -> None:
    standard = tmp_path / "standards" / "exam_001"
    (standard / "rubrics").mkdir(parents=True)
    (standard / "rubrics" / "question_001.json").write_text(
        _sample_rubric().model_dump_json(indent=2),
        encoding="utf-8",
    )

    qdir = tmp_path / "questions" / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="keep", latex="x-4<0"),
            StudentStep(step_number=2, raw_text="keep", latex="x<4"),
        ],
        student_final_answer="x<4",
    )
    qpath = qdir / "question.json"
    original = question.model_dump_json(indent=2)
    qpath.write_text(original, encoding="utf-8")

    validation = QuestionValidation(
        question_number=1,
        question_id="question_001",
        steps=[
            _step(1, ValidationStatus.VALID),
            _step(2, ValidationStatus.VALID),
        ],
        final_answer_status=_step(0, ValidationStatus.VALID),
    )
    (qdir / "validation.json").write_text(
        validation.model_dump_json(indent=2), encoding="utf-8"
    )

    grader = StepGrader(RubricLoader(standard))
    grade = GradeController(grader, standard).grade(tmp_path / "questions")

    assert (qdir / "grading.json").is_file()
    assert grade.grades[0].score == pytest.approx(10.0)
    assert qpath.read_text(encoding="utf-8") == original
    assert "keep" in qpath.read_text(encoding="utf-8")


def test_step_grader_missing_validation_errors(tmp_path: Path) -> None:
    standard = tmp_path / "standards" / "exam_001"
    (standard / "rubrics").mkdir(parents=True)
    (standard / "rubrics" / "question_001.json").write_text(
        _sample_rubric().model_dump_json(indent=2),
        encoding="utf-8",
    )
    qdir = tmp_path / "questions" / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[StudentStep(step_number=1, raw_text="", latex="x<4")],
    )
    (qdir / "question.json").write_text(
        question.model_dump_json(indent=2), encoding="utf-8"
    )

    with pytest.raises(ValidationNotFoundError):
        GradeController(StepGrader(RubricLoader(standard)), standard).grade(
            tmp_path / "questions"
        )


def test_cli_grade(tmp_path: Path, capsys) -> None:
    repo_standard = Path("data/output/standards/exam_001")
    questions_dir = tmp_path / "questions"
    qdir = questions_dir / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="x-4<0"),
            StudentStep(step_number=2, raw_text="", latex="x<4"),
        ],
        student_final_answer="x<4",
    )
    (qdir / "question.json").write_text(
        question.model_dump_json(indent=2), encoding="utf-8"
    )
    validation = QuestionValidation(
        question_number=1,
        question_id="question_001",
        steps=[
            _step(1, ValidationStatus.VALID),
            _step(2, ValidationStatus.VALID),
        ],
        final_answer_status=_step(0, ValidationStatus.VALID),
    )
    (qdir / "validation.json").write_text(
        validation.model_dump_json(indent=2), encoding="utf-8"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "questions:",
                f"  output_dir: {questions_dir.as_posix()}",
                "grading:",
                f"  standard_dir: {repo_standard.as_posix()}",
                "ollama:",
                '  reasoning_model: ""',
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "grade",
            "--questions-dir",
            str(questions_dir),
            "--standard",
            str(repo_standard),
        ]
    )

    assert exit_code == 0
    assert (qdir / "grading.json").is_file()
    out = capsys.readouterr().out
    assert "Graded 1 question(s)" in out
    assert "10.0/10" in out or "10/10" in out


def test_cli_grade_missing_validation(tmp_path: Path, capsys) -> None:
    repo_standard = Path("data/output/standards/exam_001")
    questions_dir = tmp_path / "questions"
    qdir = questions_dir / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[StudentStep(step_number=1, raw_text="", latex="x<4")],
    )
    (qdir / "question.json").write_text(
        question.model_dump_json(indent=2), encoding="utf-8"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"questions:\n  output_dir: {questions_dir.as_posix()}\n"
        f"grading:\n  standard_dir: {repo_standard.as_posix()}\n"
        'ollama:\n  reasoning_model: ""\n',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "grade",
            "--questions-dir",
            str(questions_dir),
            "--standard",
            str(repo_standard),
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "validation.json" in err
