"""Unit and CLI tests for Phase 8 reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli import main
from app.controllers.report_controller import ReportController
from app.exceptions import GradingNotFoundError
from app.functions.report_aggregate import aggregate_exam_report, summary_csv_rows
from app.models.grading import (
    ErrorType,
    QuestionGrade,
    ReviewStatus,
    StepGrade,
    StepGradeStatus,
)
from app.models.report import PromptVersions, ReportMetadata
from app.models.validation import ValidationStatus
from app.services.grading.report import JsonCsvHtmlReporter


def _step_grade(
    n: int,
    score: float,
    max_score: float,
    *,
    status: StepGradeStatus = StepGradeStatus.CORRECT,
    validation: ValidationStatus = ValidationStatus.VALID,
) -> StepGrade:
    return StepGrade(
        step_number=n,
        score=score,
        max_score=max_score,
        status=status,
        error_type=ErrorType.NONE,
        feedback="",
        validation_status=validation,
    )


def _grade(
    number: int,
    score: float,
    maximum: float,
    *,
    review: ReviewStatus = ReviewStatus.AUTO_ACCEPT,
    steps: int = 2,
) -> QuestionGrade:
    per = maximum / max(steps, 1)
    return QuestionGrade(
        question_id=f"question_{number:03d}",
        question_number=number,
        score=score,
        maximum_score=maximum,
        steps=[
            _step_grade(i + 1, per if i < steps - 1 else score - per * (steps - 1), per)
            for i in range(steps)
        ],
        review_status=review,
    )


def _metadata(tmp_path: Path) -> ReportMetadata:
    return ReportMetadata(
        generated_at="2026-01-01T00:00:00+00:00",
        standard_dir=tmp_path / "standards" / "exam_001",
        questions_dir=tmp_path / "questions",
        student_id="student_001",
        vision_model="vision-test",
        reasoning_model="reason-test",
        prompt_versions=PromptVersions(
            recognition="recognition-v1",
            validation="validation-v1",
            grading="grading-v1",
        ),
    )


def test_aggregate_full_auto_accept(tmp_path: Path) -> None:
    report = aggregate_exam_report(
        [_grade(1, 10.0, 10.0)],
        _metadata(tmp_path),
    )
    assert report.total_score == pytest.approx(10.0)
    assert report.maximum_total == pytest.approx(10.0)
    assert report.overall_status == ReviewStatus.AUTO_ACCEPT
    assert len(report.questions) == 1


def test_aggregate_review_required_overall(tmp_path: Path) -> None:
    report = aggregate_exam_report(
        [
            _grade(1, 10.0, 10.0),
            _grade(2, 5.0, 10.0, review=ReviewStatus.REVIEW_REQUIRED),
        ],
        _metadata(tmp_path),
    )
    assert report.total_score == pytest.approx(15.0)
    assert report.overall_status == ReviewStatus.REVIEW_REQUIRED
    header, row = summary_csv_rows(report)
    assert header == ["student_id", "q1", "q2", "total", "status"]
    assert row[0] == "student_001"
    assert row[1] == "10"
    assert row[2] == "5"
    assert row[3] == "15"
    assert row[4] == "REVIEW_REQUIRED"


def test_reporter_writes_three_formats(tmp_path: Path) -> None:
    report = aggregate_exam_report([_grade(1, 10.0, 10.0)], _metadata(tmp_path))
    out = tmp_path / "output" / "exam_001"
    paths = JsonCsvHtmlReporter().write(report, out)
    assert len(paths) == 3
    assert (out / "report.json").is_file()
    assert (out / "summary.csv").is_file()
    assert (out / "report.html").is_file()
    csv_text = (out / "summary.csv").read_text(encoding="utf-8")
    assert "student_id,q1,total,status" in csv_text
    assert "student_001,10,10,AUTO_ACCEPT" in csv_text
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "student_001" in html
    assert "AUTO_ACCEPT" in html
    payload = (out / "report.json").read_text(encoding="utf-8")
    assert '"total_score": 10.0' in payload or '"total_score": 10' in payload
    assert "recognition-v1" in payload


def test_controller_missing_grading_errors(tmp_path: Path) -> None:
    questions = tmp_path / "questions"
    questions.mkdir()
    with pytest.raises(GradingNotFoundError):
        ReportController(
            JsonCsvHtmlReporter(),
            standard_dir=tmp_path / "standards" / "exam_001",
        ).report(questions, tmp_path / "out")


def test_controller_does_not_mutate_grading(tmp_path: Path) -> None:
    questions = tmp_path / "questions"
    qdir = questions / "question_001"
    qdir.mkdir(parents=True)
    grade = _grade(1, 10.0, 10.0)
    gpath = qdir / "grading.json"
    original = grade.model_dump_json(indent=2)
    gpath.write_text(original, encoding="utf-8")
    # Also leave a question.json that must stay untouched
    qpath = qdir / "question.json"
    qpath.write_text('{"keep": true}', encoding="utf-8")

    result = ReportController(
        JsonCsvHtmlReporter(),
        standard_dir=tmp_path / "standards",
        vision_model="v",
        reasoning_model="r",
    ).report(questions, tmp_path / "out", student_id="student_001")

    assert result.exam_report.total_score == pytest.approx(10.0)
    assert gpath.read_text(encoding="utf-8") == original
    assert qpath.read_text(encoding="utf-8") == '{"keep": true}'
    assert result.report_json_path.is_file()


def test_cli_report(tmp_path: Path, capsys) -> None:
    questions = tmp_path / "questions"
    qdir = questions / "question_001"
    qdir.mkdir(parents=True)
    (qdir / "grading.json").write_text(
        _grade(1, 10.0, 10.0).model_dump_json(indent=2),
        encoding="utf-8",
    )
    out = tmp_path / "output" / "exam_001"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "questions:",
                f"  output_dir: {questions.as_posix()}",
                "grading:",
                f"  standard_dir: {(tmp_path / 'standards').as_posix()}",
                "report:",
                f"  output_dir: {out.as_posix()}",
                "ollama:",
                '  vision_model: "vision-test"',
                '  reasoning_model: ""',
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "report",
            "--questions-dir",
            str(questions),
            "--output",
            str(out),
            "--student-id",
            "student_001",
        ]
    )

    assert exit_code == 0
    assert (out / "report.json").is_file()
    assert (out / "summary.csv").is_file()
    assert (out / "report.html").is_file()
    assert "Report for student_001" in capsys.readouterr().out


def test_cli_report_missing_grading(tmp_path: Path, capsys) -> None:
    questions = tmp_path / "questions"
    questions.mkdir()
    out = tmp_path / "out"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"questions:\n  output_dir: {questions.as_posix()}\n"
        f"report:\n  output_dir: {out.as_posix()}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "report",
            "--questions-dir",
            str(questions),
            "--output",
            str(out),
        ]
    )

    assert exit_code == 1
    assert "grading.json" in capsys.readouterr().err
