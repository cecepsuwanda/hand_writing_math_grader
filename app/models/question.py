"""Question domain schemas (merged multi-page extraction)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.recognition import Region


class SegmentationStatus(str, Enum):
    MERGED = "merged"
    PROVISIONAL = "provisional"


class StudentStep(BaseModel):
    step_number: int
    raw_text: str
    latex: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    page_number: int | None = None


class ImageRegionRef(BaseModel):
    page_number: int
    region: Region | None = None


class Question(BaseModel):
    question_id: str
    question_number: int
    page_references: list[int] = Field(default_factory=list)
    image_regions: list[ImageRegionRef] = Field(default_factory=list)
    student_steps: list[StudentStep] = Field(default_factory=list)
    student_final_answer: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    segmentation_status: SegmentationStatus = SegmentationStatus.MERGED


class ExtractResult(BaseModel):
    questions: list[Question]
    output_dir: Path
    artifact_paths: list[Path] = Field(default_factory=list)
