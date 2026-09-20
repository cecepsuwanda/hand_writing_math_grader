"""Grading domain schemas and rubric definitions."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.validation import ValidationStatus


class ErrorType(str, Enum):
    NONE = "none"
    CONCEPTUAL = "conceptual"
    CALCULATION = "calculation"
    TRANSCRIPTION = "transcription"
    CARRY_FORWARD = "carry_forward"
    UNCERTAIN = "uncertain"


class StepGradeStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    REVIEW = "review"


class ReviewStatus(str, Enum):
    AUTO_ACCEPT = "AUTO_ACCEPT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RubricCriterion(BaseModel):
    id: str
    points: float = Field(ge=0)


class Rubric(BaseModel):
    question: int
    maximum_score: float = Field(gt=0)
    criteria: list[RubricCriterion] = Field(default_factory=list)


class StepGrade(BaseModel):
    step_number: int
    score: float
    max_score: float
    status: StepGradeStatus
    error_type: ErrorType = ErrorType.NONE
    feedback: str = ""
    validation_status: ValidationStatus


class QuestionGrade(BaseModel):
    question_id: str
    question_number: int
    score: float
    maximum_score: float
    steps: list[StepGrade] = Field(default_factory=list)
    final_answer: StepGrade | None = None
    review_status: ReviewStatus = ReviewStatus.AUTO_ACCEPT
    standard_final_status: ValidationStatus | None = None
    standard_step_statuses: dict[str, str] | None = None


class GradeResult(BaseModel):
    grades: list[QuestionGrade] = Field(default_factory=list)
    questions_dir: Path
    standard_dir: Path
    artifact_paths: list[Path] = Field(default_factory=list)


class FeedbackAnnotation(BaseModel):
    error_type: ErrorType = ErrorType.NONE
    feedback: str = ""
