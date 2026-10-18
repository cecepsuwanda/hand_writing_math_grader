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


QuestionKey = tuple[int, str]


def question_key(key: int | QuestionKey) -> QuestionKey:
    """``3`` → ``(3, "")``; ``(1, "a")`` unchanged (number + sub-soal label)."""
    return (key, "") if isinstance(key, int) else (key[0], key[1])


def aggregate_exam_report(
    grades: list[QuestionGrade],
    metadata: ReportMetadata,
    expected_maximums: Mapping[int | QuestionKey, float] | None = None,
    missing_labels: Mapping[int | QuestionKey, str] | None = None,
) -> ExamReport:
    """``expected_maximums`` (question key → rubric maximum) adds ungraded questions as 0.

    Keys are a question number or ``(number, part_label)`` for a sub-soal.
    ``missing_labels`` says why such a row has no grade (default ``TIDAK DIJAWAB``).
    """
    rows = [
        QuestionReportRow(
            question_id=g.question_id,
            question_number=g.question_number,
            part_label=g.part_label,
            score=g.score,
            maximum_score=g.maximum_score,
            review_status=g.review_status,
            step_count=sum(1 for s in g.steps if s.step_number > 0),
            part_statuses=dict(g.part_statuses or {}),
        )
        for g in grades
    ]
    graded = {(g.question_number, g.part_label) for g in grades}
    labels = {question_key(key): label for key, label in (missing_labels or {}).items()}
    for raw_key, maximum in (expected_maximums or {}).items():
        number, part_label = question_key(raw_key)
        if (number, part_label) in graded:
            continue
        rows.append(
            QuestionReportRow(
                question_id=question_dir_name(number, part_label),
                question_number=number,
                part_label=part_label,
                score=0.0,
                maximum_score=maximum,
                review_status=ReviewStatus.REVIEW_REQUIRED,
                missing=True,
                missing_label=labels.get((number, part_label), MISSING_UNANSWERED),
            )
        )
    rows.sort(key=lambda r: (r.question_number, r.part_label))
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
        header.append(f"q{q.ref}")
        row.append(format_score(q.score))
    header.extend(["total", "status"])
    row.extend([format_score(report.total_score), report.overall_status.value])
    return header, row


def format_score(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"
