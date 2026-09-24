"""Pure aggregation: QuestionGrade list + metadata → ExamReport."""

from __future__ import annotations

from app.models.grading import QuestionGrade, ReviewStatus
from app.models.report import ExamReport, QuestionReportRow, ReportMetadata


def aggregate_exam_report(
    grades: list[QuestionGrade],
    metadata: ReportMetadata,
) -> ExamReport:
    ordered = sorted(grades, key=lambda g: g.question_number)
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
        for g in ordered
    ]
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
        row.append(_format_score(q.score))
    header.extend(["total", "status"])
    row.extend([_format_score(report.total_score), report.overall_status.value])
    return header, row


def _format_score(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"
