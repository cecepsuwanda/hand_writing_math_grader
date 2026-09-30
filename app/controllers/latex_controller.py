"""Build student.tex artifacts for every question folder."""

from __future__ import annotations

from pathlib import Path

from app.interfaces.latex_builder import LatexDocumentBuilder
from app.models.latex import LatexResult


class LatexController:
    def __init__(self, builder: LatexDocumentBuilder) -> None:
        self._builder = builder

    def build(self, questions_dir: Path) -> LatexResult:
        return self._builder.build_dir(Path(questions_dir))
