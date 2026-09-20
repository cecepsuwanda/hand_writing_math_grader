"""Process pipeline domain schemas."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.grading import ReviewStatus


class ProcessStage(str, Enum):
    RENDER = "PDF rendering"
    RECOGNIZE = "Recognition"
    EXTRACT = "Question extraction"
    LATEX = "LaTeX"
    VALIDATE = "Validation"
    GRADE = "Grading"
    REPORT = "Report"


PROCESS_STAGES: tuple[ProcessStage, ...] = (
    ProcessStage.RENDER,
    ProcessStage.RECOGNIZE,
    ProcessStage.EXTRACT,
    ProcessStage.LATEX,
    ProcessStage.VALIDATE,
    ProcessStage.GRADE,
    ProcessStage.REPORT,
)


class ProcessProgress(BaseModel):
    stage: ProcessStage
    completed: int
    total: int = 7


class QuestionScoreSummary(BaseModel):
    question_id: str
    question_number: int
    score: float
    maximum_score: float
    review_status: ReviewStatus


class ProcessResult(BaseModel):
    student_id: str
    questions: list[QuestionScoreSummary] = Field(default_factory=list)
    total_score: float = 0.0
    maximum_total: float = 0.0
    overall_status: ReviewStatus = ReviewStatus.AUTO_ACCEPT
    output_dir: Path
    report_json_path: Path | None = None
    summary_csv_path: Path | None = None
    report_html_path: Path | None = None
    questions_dir: Path
    pages_dir: Path
    recognition_dir: Path
