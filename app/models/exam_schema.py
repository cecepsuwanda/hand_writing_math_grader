"""Exam schema from kunci_jawaban (deterministic, no LLM)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.recognition import SymbolicPayload


class ExamPart(BaseModel):
    kind: Literal["algebra", "figure", "hp"]
    order: int = Field(ge=1)


class ExamQuestion(BaseModel):
    number: int = Field(ge=1)
    stem: str
    stem_symbolic: SymbolicPayload | None = None
    steps: list[str] = Field(default_factory=list)
    steps_symbolic: list[SymbolicPayload | None] = Field(default_factory=list)
    final: str = ""
    final_symbolic: SymbolicPayload | None = None
    expects_figure: bool = False
    parts: list[ExamPart] = Field(default_factory=list)


class ExamSchema(BaseModel):
    source: str = ""
    questions: list[ExamQuestion] = Field(default_factory=list)
