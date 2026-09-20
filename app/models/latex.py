"""LaTeX artifact schemas."""

from pathlib import Path

from pydantic import BaseModel, Field


class LatexArtifact(BaseModel):
    question_id: str
    path: Path


class LatexResult(BaseModel):
    artifacts: list[LatexArtifact] = Field(default_factory=list)
    questions_dir: Path
