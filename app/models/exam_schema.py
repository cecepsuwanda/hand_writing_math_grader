"""Exam schema from kunci_jawaban (deterministic, no LLM)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.recognition import SymbolicPayload

ExamPartKind = Literal[
    "algebra",
    "critical_points",
    "sign_chart",
    "figure",
    "hp",
]

ExamMilestoneRole = Literal["critical_points", "sign_chart", "hp"]


class ExamPart(BaseModel):
    kind: ExamPartKind
    order: int = Field(ge=1)


class ExamMethod(BaseModel):
    id: str
    label: str = ""
    steps: list[str] = Field(default_factory=list)
    steps_symbolic: list[SymbolicPayload | None] = Field(default_factory=list)


class ExamMilestone(BaseModel):
    role: ExamMilestoneRole
    latex: str = ""
    symbolic: SymbolicPayload | None = None
    steps: list[str] = Field(default_factory=list)
    steps_symbolic: list[SymbolicPayload | None] = Field(default_factory=list)


class ExamQuestion(BaseModel):
    number: int = Field(ge=1)
    stem: str
    stem_symbolic: SymbolicPayload | None = None
    steps: list[str] = Field(default_factory=list)
    steps_symbolic: list[SymbolicPayload | None] = Field(default_factory=list)
    methods: list[ExamMethod] = Field(default_factory=list)
    milestones: list[ExamMilestone] = Field(default_factory=list)
    final: str = ""
    final_symbolic: SymbolicPayload | None = None
    expects_figure: bool = False
    parts: list[ExamPart] = Field(default_factory=list)


class ExamSchema(BaseModel):
    source: str = ""
    questions: list[ExamQuestion] = Field(default_factory=list)
