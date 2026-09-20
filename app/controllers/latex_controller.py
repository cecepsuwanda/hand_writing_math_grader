from pathlib import Path

from app.models.latex import LatexResult
from app.services.latex.builder import LatexBuilder


class LatexController:
    def __init__(self, builder: LatexBuilder) -> None:
        self._builder = builder

    def build(self, questions_dir: Path) -> LatexResult:
        return self._builder.build_dir(questions_dir)
