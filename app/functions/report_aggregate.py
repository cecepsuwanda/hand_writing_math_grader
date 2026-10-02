"""Pure aggregation: QuestionGrade list + metadata → ExamReport."""

from __future__ import annotations

from collections.abc import Mapping

from app.functions.question_names import question_dir_name
from app.models.grading import QuestionGrade, ReviewStatus
from app.models.report import (
    MISSING_UNANSWERED,
    ExamReport,
    QuestionReportRow,
    ReportMetadata,
)


def aggregate_exam_report(
    grades: list[QuestionGrade],
    metadata: ReportMetadata,
    expected_maximums: Mapping[int, float] | None = None,
    missing_labels: Mapping[int, str] | None = None,
) -> ExamReport:
    """``expected_maximums`` (question number → rubric maximum) adds ungraded questions as 0.

    ``missing_labels`` says why such a row has no grade (default ``TIDAK DIJAWAB``).
    """
    rows = [
        QuestionReportRow(
            question_id=g.question_id,
            question_number=g.question_number,
            score=g.score,
            maximum_score=g.maximum_score,
            review_status=g.review_status,
            step_count=sum(1 for s in g.steps if s.step_number > 0),
            part_statuses=dict(g.part_statuses or {}),
        )
        for g in grades
    ]
    graded = {g.question_number for g in grades}
    rows.extend(
        QuestionReportRow(
            question_id=question_dir_name(number),
            question_number=number,
            score=0.0,
            maximum_score=maximum,
            review_status=ReviewStatus.REVIEW_REQUIRED,
            missing=True,
            missing_label=(missing_labels or {}).get(number, MISSING_UNANSWERED),
        )
        for number, maximum in (expected_maximums or {}).items()
        if number not in graded
    )
    rows.sort(key=lambda r: r.question_number)
    total = round(sum(r.score for r in rows), 4)
    maximum = round(sum(r.maximum_score for r in rows), 4)
    overall = ReviewStatus.AUTO_ACCEPT
    if any(r.review_status == ReviewStatus.REVIEW_REQUIRED for r in rows):
        overall = ReviewStatus.REVIEW_REQUIRED
    return ExamReport(
        metadata=metadata,
        questions=rows,
        total_score=total,
        maximum_total=maximum,
        overall_status=overall,
    )


def summary_csv_rows(report: ExamReport) -> tuple[list[str], list[str]]:
    """Return (header, data_row) for a single-student summary CSV."""
    header = ["student_id"]
    row = [report.metadata.student_id]
    for q in report.questions:
        header.append(f"q{q.question_number}")
        row.append(format_score(q.score))
    header.extend(["total", "status"])
    row.extend([format_score(report.total_score), report.overall_status.value])
    return header, row


def format_score(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"
