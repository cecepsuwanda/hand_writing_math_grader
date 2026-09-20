"""Validation domain schemas (SymPy / later LLM)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


class ValidationMethod(str, Enum):
    SYMPY = "sympy"
    PARSE = "parse"
    LLM = "llm"


class LlmJudgement(BaseModel):
    status: ValidationStatus
    reason: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class StepValidation(BaseModel):
    step_number: int
    status: ValidationStatus
    method: ValidationMethod
    reason: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class QuestionValidation(BaseModel):
    question_number: int
    question_id: str = ""
    steps: list[StepValidation] = Field(default_factory=list)
    final_answer_status: StepValidation | None = None


class ValidateResult(BaseModel):
    validations: list[QuestionValidation] = Field(default_factory=list)
    questions_dir: Path
    artifact_paths: list[Path] = Field(default_factory=list)
