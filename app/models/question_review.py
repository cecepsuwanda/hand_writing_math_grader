"""Human review of extracted ``question.json`` before LaTeX / validation."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.question import Question


class ReviewFlag(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    UNCERTAIN_MARK = "uncertain_mark"
    MISSING_SYMBOLIC = "missing_symbolic"


class StepReviewFlags(BaseModel):
    step_number: int
    flags: list[ReviewFlag] = Field(default_factory=list)


class QuestionReviewItem(BaseModel):
    path: Path
    question: Question
    flagged_steps: list[StepReviewFlags] = Field(default_factory=list)


class QuestionReviewResult(BaseModel):
    questions_dir: Path
    items: list[QuestionReviewItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    edited_ids: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors
