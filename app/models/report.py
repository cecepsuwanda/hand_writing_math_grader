"""Report domain schemas for exam-level summary artifacts."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.models.grading import ReviewStatus


class PromptVersions(BaseModel):
    recognition: str = ""
    validation: str = ""
    grading: str = ""


class ReportMetadata(BaseModel):
    generated_at: str
    standard_dir: Path
    questions_dir: Path
    student_id: str
    vision_model: str = ""
    reasoning_model: str = ""
    prompt_versions: PromptVersions = Field(default_factory=PromptVersions)


class QuestionReportRow(BaseModel):
    question_id: str
    question_number: int
    score: float
    maximum_score: float
    review_status: ReviewStatus
    step_count: int = 0


class ExamReport(BaseModel):
    metadata: ReportMetadata
    questions: list[QuestionReportRow] = Field(default_factory=list)
    total_score: float = 0.0
    maximum_total: float = 0.0
    overall_status: ReviewStatus = ReviewStatus.AUTO_ACCEPT


class ReportResult(BaseModel):
    exam_report: ExamReport
    output_dir: Path
    report_json_path: Path
    summary_csv_path: Path
    report_html_path: Path
