"""Tests for standard final-answer extract + compare + grading wire."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.controllers.grade_controller import GradeController
from app.functions.score_aggregate import aggregate_question_grade
from app.functions.standard_extract import (
    extract_final_answer_from_tex,
    extract_solution_steps_from_tex,
    standard_solution_path,
)
from app.models.grading import Rubric, RubricCriterion
from app.models.question import Question, StudentStep
from app.models.validation import (
    QuestionValidation,
    StepValidation,
    ValidationMethod,
    ValidationStatus,
)
from app.services.grading.rubric import RubricLoader
from app.services.grading.standard_comparer import StandardFinalComparer
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


def test_extract_final_answer_from_tex() -> None:
    tex = "% header\n\\begin{aligned}\nx &< 4\n\\end{aligned}\n\n% final answer\nx < 4\n"
    assert extract_final_answer_from_tex(tex) == "x < 4"
    assert extract_final_answer_from_tex("no marker here") is None


def test_extract_solution_steps_from_tex_q001() -> None:
    tex = Path(
        "data/output/standards/exam_001/solutions/question_001.tex"
    ).read_text(encoding="utf-8")
    steps = extract_solution_steps_from_tex(tex)
    assert len(steps) >= 2
    assert "2x" in steps[0].replace(" ", "")
    assert "x" in steps[-1] and "4" in steps[-1]


def test_extract_solution_steps_ignores_final_answer_section() -> None:
    tex = (
        "\\begin{aligned}\nx &< 4 \\\\\n\\end{aligned}\n\n"
        "% final answer\nx < 4\n"
    )
    steps = extract_solution_steps_from_tex(tex)
    assert steps == ["x < 4"]


def test_standard_solution_path() -> None:
    path = standard_solution_path(Path("data/output/standards/exam_001"), 1)
    assert path.as_posix().endswith("solutions/question_001.tex")


def test_comparer_match_q1_repo_standard() -> None:
    standard = Path("data/output/standards/exam_001")
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x-3<5"),
            StudentStep(step_number=2, raw_text="", latex="x<4"),
        ],
        student_final_answer="x < 4",
    )
    result = StandardFinalComparer(standard).compare(question)
    assert result is not None
    status, reason = result
    assert status == ValidationStatus.VALID
    assert "matches" in reason


def test_comparer_mismatch_invalid() -> None:
    standard = Path("data/output/standards/exam_001")
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[StudentStep(step_number=1, raw_text="", latex="x<5")],
        student_final_answer="x < 5",
    )
    result = StandardFinalComparer(standard).compare(question)
    assert result is not None
    assert result[0] == ValidationStatus.INVALID


def test_comparer_missing_solution_returns_none(tmp_path: Path) -> None:
    standard = tmp_path / "exam"
    (standard / "solutions").mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_final_answer="x<4",
    )
    assert StandardFinalComparer(standard).compare(question) is None
    assert StandardFinalComparer(standard).compare_steps(question) is None


def test_compare_steps_match_q001_order() -> None:
    standard = Path("data/output/standards/exam_001")
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x-3<5"),
            StudentStep(step_number=2, raw_text="", latex="2x<8"),
            StudentStep(step_number=3, raw_text="", latex="x<4"),
        ],
        student_final_answer="x < 4",
    )
    results = StandardFinalComparer(standard).compare_steps(question)
    assert results is not None
    assert results[1][0] == ValidationStatus.VALID
    assert results[2][0] == ValidationStatus.VALID
    assert results[3][0] == ValidationStatus.VALID


def test_compare_steps_mismatch_invalid() -> None:
    standard = Path("data/output/standards/exam_001")
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x-3<5"),
            StudentStep(step_number=2, raw_text="", latex="2x<9"),
            StudentStep(step_number=3, raw_text="", latex="x<4"),
        ],
    )
    results = StandardFinalComparer(standard).compare_steps(question)
    assert results is not None
    assert results[1][0] == ValidationStatus.VALID
    assert results[2][0] == ValidationStatus.INVALID
    assert results[3][0] == ValidationStatus.VALID


def test_aggregate_standard_step_mismatch_cuts_step_score() -> None:
    validation = QuestionValidation(
        question_number=1,
        question_id="question_001",
        steps=[
            _step(1, ValidationStatus.VALID),
            _step(2, ValidationStatus.VALID),
            _step(3, ValidationStatus.VALID),
        ],
        final_answer_status=_step(0, ValidationStatus.VALID),
    )
    grade = aggregate_question_grade(
        question_id="question_001",
        question_number=1,
        validation=validation,
        rubric=_sample_rubric(),
        standard_final_status=ValidationStatus.VALID,
        standard_final_reason="matches",
        standard_step_results={
            1: (ValidationStatus.VALID, "step matches standard"),
            2: (ValidationStatus.INVALID, "step differs from standard"),
            3: (ValidationStatus.VALID, "step matches standard"),
        },
    )
    assert grade.steps[1].score == pytest.approx(0.0)
    assert "standard:" in grade.steps[1].feedback
    assert grade.standard_step_statuses == {
        "1": "valid",
        "2": "invalid",
        "3": "valid",
    }
    assert grade.score == pytest.approx(
        grade.steps[0].score + grade.steps[2].score + 2.0
    )


def test_comparer_prose_uncertain(tmp_path: Path) -> None:
    standard = tmp_path / "exam"
    sol = standard / "solutions"
    sol.mkdir(parents=True)
    (sol / "question_001.tex").write_text(
        "% final answer\nf kontinu di a\n", encoding="utf-8"
    )
    question = Question(
        question_id="question_001",
        question_number=1,
        student_final_answer="f kontinu di a",
    )
    result = StandardFinalComparer(standard).compare(question)
    assert result is not None
    assert result[0] == ValidationStatus.UNCERTAIN


def test_aggregate_standard_mismatch_zeros_final_only() -> None:
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
        standard_final_status=ValidationStatus.INVALID,
        standard_final_reason="differs from standard",
    )
    # Steps 8 + final 0
    assert grade.score == pytest.approx(8.0)
    assert grade.final_answer is not None
    assert grade.final_answer.score == pytest.approx(0.0)
    assert grade.standard_final_status == ValidationStatus.INVALID
    assert "standard:" in grade.final_answer.feedback


def test_step_grader_with_standard_match(tmp_path: Path) -> None:
    standard = tmp_path / "standards" / "exam_001"
    (standard / "rubrics").mkdir(parents=True)
    (standard / "solutions").mkdir(parents=True)
    (standard / "rubrics" / "question_001.json").write_text(
        _sample_rubric().model_dump_json(indent=2), encoding="utf-8"
    )
    (standard / "solutions" / "question_001.tex").write_text(
        "% final answer\nx < 4\n", encoding="utf-8"
    )

    qdir = tmp_path / "questions" / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x-3<5"),
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

    grader = StepGrader(
        RubricLoader(standard),
        standard_comparer=StandardFinalComparer(standard),
    )
    grade = GradeController(grader, standard).grade(tmp_path / "questions")
    assert grade.grades[0].score == pytest.approx(10.0)
    assert grade.grades[0].standard_final_status == ValidationStatus.VALID


def test_step_grader_with_standard_mismatch(tmp_path: Path) -> None:
    standard = tmp_path / "standards" / "exam_001"
    (standard / "rubrics").mkdir(parents=True)
    (standard / "solutions").mkdir(parents=True)
    (standard / "rubrics" / "question_001.json").write_text(
        _sample_rubric().model_dump_json(indent=2), encoding="utf-8"
    )
    (standard / "solutions" / "question_001.tex").write_text(
        "% final answer\nx < 4\n", encoding="utf-8"
    )

    qdir = tmp_path / "questions" / "question_001"
    qdir.mkdir(parents=True)
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x-3<5"),
            StudentStep(step_number=2, raw_text="", latex="x<4"),
        ],
        student_final_answer="x<5",
    )
    (qdir / "question.json").write_text(
        question.model_dump_json(indent=2), encoding="utf-8"
    )
    # Consistency still VALID (last step matches final) — standard should cut final only
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

    grader = StepGrader(
        RubricLoader(standard),
        standard_comparer=StandardFinalComparer(standard),
    )
    grade = GradeController(grader, standard).grade(tmp_path / "questions")
    g = grade.grades[0]
    assert g.standard_final_status == ValidationStatus.INVALID
    assert g.final_answer is not None
    assert g.final_answer.score == pytest.approx(0.0)
    # Two steps share 8 points equally → 4 each; final 0 → 8
    assert g.score == pytest.approx(8.0)
