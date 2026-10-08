"""Question → crop mapping (``crops/question_crops/question_NNN.json``)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

QuestionCropMap = dict[int, list[str]]


class QuestionCrops(BaseModel):
    """Crops (by file name) where one exam question's answer is written."""

    question_number: int = Field(ge=1)
    stem: str = ""
    crops: list[str] = Field(default_factory=list)


class CropRef(BaseModel):
    """One crop PNG in reading order (page, then region order)."""

    page_number: int = Field(ge=1)
    order: int = 0
    name: str


class QuestionCropsReport(BaseModel):
    """Validation of the question → crop mapping against kunci + regions."""

    errors: list[str] = Field(default_factory=list)
    missing_questions: list[int] = Field(default_factory=list)
    unassigned_crops: list[str] = Field(default_factory=list)
    # Warning only: the crop followed the previous question.
    unreadable_crops: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class LabelSource(StrEnum):
    """How a question → crop mapping was produced."""

    VISION = "vision"
    SEQUENTIAL = "sequential"
    RELOAD = "reload"


class QuestionLabelResult(BaseModel):
    mapping: QuestionCropMap = Field(default_factory=dict)
    report: QuestionCropsReport
    json_dir: Path
    source: LabelSource
