"""Port for building ``student.tex`` per question."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.models.latex import LatexResult


@runtime_checkable
class LatexDocumentBuilder(Protocol):
    def build_dir(self, questions_dir: Path) -> LatexResult:
        """Write ``student.tex`` for every ``question_NNN`` folder."""
