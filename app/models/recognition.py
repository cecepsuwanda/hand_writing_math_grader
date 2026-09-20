"""Recognition domain schemas (vision output)."""

from pathlib import Path

from pydantic import BaseModel, Field


class Region(BaseModel):
    x: int
    y: int
    width: int
    height: int


class RecognizedStep(BaseModel):
    step_number: int
    raw_text: str
    latex: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RecognizedQuestion(BaseModel):
    question_number: int
    region: Region | None = None
    steps: list[RecognizedStep] = Field(default_factory=list)
    final_answer: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PageRecognition(BaseModel):
    page_number: int
    questions: list[RecognizedQuestion] = Field(default_factory=list)
    prompt_version: str = ""
    model: str = ""


class RecognizeResult(BaseModel):
    pages: list[PageRecognition]
    output_dir: Path
    artifact_paths: list[Path] = Field(default_factory=list)
