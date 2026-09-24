"""Question domain schemas (merged multi-page extraction)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.recognition import Region, StepRole, SymbolicPayload


class SegmentationStatus(str, Enum):
    MERGED = "merged"
    PROVISIONAL = "provisional"


class StudentStep(BaseModel):
    step_number: int
    raw_text: str
    # Deprecated in JSON pipeline: leave empty; use symbolic for SymPy.
    latex: str = ""
    symbolic: SymbolicPayload | None = None
    role: StepRole | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    page_number: int | None = None


class ImageRegionRef(BaseModel):
    page_number: int
    region: Region | None = None
    region_type: str | None = None
    crop_path: str = ""


class FigureRef(BaseModel):
    path: str
    caption: str = ""
    page_number: int | None = None
    symbolic: SymbolicPayload | None = None


class Question(BaseModel):
    question_id: str
    question_number: int
    page_references: list[int] = Field(default_factory=list)
    image_regions: list[ImageRegionRef] = Field(default_factory=list)
    student_steps: list[StudentStep] = Field(default_factory=list)
    student_final_answer: str = ""
    student_final_symbolic: SymbolicPayload | None = None
    figure_refs: list[FigureRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    segmentation_status: SegmentationStatus = SegmentationStatus.MERGED


class ExtractResult(BaseModel):
    questions: list[Question]
    output_dir: Path
    artifact_paths: list[Path] = Field(default_factory=list)
