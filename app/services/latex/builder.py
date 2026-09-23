"""Build per-question student.tex from extracted Question JSON."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import LatexBuildError, QuestionsNotFoundError
from app.functions.latex_transforms import build_student_latex
from app.functions.question_names import question_artifact_filename, student_tex_filename
from app.models.latex import LatexArtifact, LatexResult
from app.models.question import Question

logger = logging.getLogger(__name__)


class LatexBuilder:
    def build_dir(self, questions_dir: Path) -> LatexResult:
        questions_dir = Path(questions_dir)
        question_paths = sorted(questions_dir.glob(f"*/{question_artifact_filename()}"))
        if not question_paths:
            raise QuestionsNotFoundError(questions_dir)

        artifacts: list[LatexArtifact] = []
        for path in question_paths:
            question = self._load_question(path)
            # Snapshot before write to ensure we never mutate question.json
            original = path.read_text(encoding="utf-8")
            tex_path = self._write_student_tex(path.parent, question)
            after = path.read_text(encoding="utf-8")
            if after != original:
                raise LatexBuildError(
                    question.question_id,
                    "question.json was modified while writing student.tex",
                )
            artifacts.append(
                LatexArtifact(question_id=question.question_id, path=tex_path)
            )

        logger.info(
            "Wrote %s student.tex file(s) under %s",
            len(artifacts),
            questions_dir,
        )
        return LatexResult(artifacts=artifacts, questions_dir=questions_dir)

    def _load_question(self, path: Path) -> Question:
        try:
            return Question.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise LatexBuildError(path.parent.name, str(exc)) from exc

    def _write_student_tex(self, question_dir: Path, question: Question) -> Path:
        try:
            content = build_student_latex(question, question_dir=question_dir)
            path = question_dir / student_tex_filename()
            path.write_text(content, encoding="utf-8")
            return path
        except OSError as exc:
            raise LatexBuildError(question.question_id, str(exc)) from exc
