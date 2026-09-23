"""Recognition domain schemas (vision output)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Region(BaseModel):
    x: float
    y: float
    width: float
    height: float


SymbolicKind = Literal[
    "relation",
    "expression",
    "limit",
    "derivative",
    "integral",
    "matrix",
    "figure",
]

RegionType = Literal["solution", "math_block", "figure"]


class SymbolicPayload(BaseModel):
    kind: SymbolicKind
    repr: str = ""


class DetectedRegion(BaseModel):
    type: RegionType
    region: Region
    question_number: int = 0
    order: int = 0


class RecognizedStep(BaseModel):
    step_number: int
    raw_text: str
    # Deprecated: new pipeline leaves this empty; LaTeX lives only in .tex artifacts.
    latex: str = ""
    symbolic: SymbolicPayload | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RecognizedQuestion(BaseModel):
    question_number: int
    region: Region | None = None
    region_type: RegionType | None = None
    crop_path: str = ""
    steps: list[RecognizedStep] = Field(default_factory=list)
    final_answer: str = ""
    final_answer_symbolic: SymbolicPayload | None = None
    # Recognition-only; copied to sidecar .tex during extract, not into question.json.
    latex_document: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Audit metadata
    source: str = ""
    review_required: bool = False
    reconcile_note: str = ""


class PageRecognition(BaseModel):
    page_number: int
    questions: list[RecognizedQuestion] = Field(default_factory=list)
    prompt_version: str = ""
    model: str = ""
    region_source: str = ""
    review_required: bool = False


class RecognizeResult(BaseModel):
    pages: list[PageRecognition]
    output_dir: Path
    artifact_paths: list[Path] = Field(default_factory=list)
