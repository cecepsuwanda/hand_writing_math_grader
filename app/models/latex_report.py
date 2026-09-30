"""View-models for ``report.tex.j2``; all strings are already LaTeX-safe."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LatexStepRow(BaseModel):
    """One OCR step with its grade."""

    number: str
    ocr: str
    role: str = ""
    status: str = ""
    status_color: str = "black"
    score: str = ""
    comment: str = ""


class LatexFigureRow(BaseModel):
    caption: str = ""
    symbolic: str = ""


class LatexQuestionView(BaseModel):
    title: str
    stem: str = ""
    images: list[str] = Field(default_factory=list)
    missing_images: list[str] = Field(default_factory=list)
    steps: list[LatexStepRow] = Field(default_factory=list)
    parts: list[LatexStepRow] = Field(default_factory=list)
    final: LatexStepRow | None = None
    figures: list[LatexFigureRow] = Field(default_factory=list)
    score: str = ""
    maximum: str = ""
    review_status: str = ""
    graded: bool = False


class LatexSummaryRow(BaseModel):
    number: int
    score: str
    maximum: str
    status: str


class LatexReportView(BaseModel):
    student_id: str
    total: str
    maximum: str
    overall_status: str
    summary: list[LatexSummaryRow] = Field(default_factory=list)
    questions: list[LatexQuestionView] = Field(default_factory=list)
    generated_at: str = ""
    vision_model: str = ""
    reasoning_model: str = ""
    prompt_versions: str = ""
