"""Human checkpoint: review extracted question.json before LaTeX / validation."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import QuestionArtifactsInvalidError
from app.functions.question_review import review_flags
from app.functions.question_review_artifact import (
    drop_latex_sources,
    load_question_artifacts,
    stale_latex_sources,
    write_reviewed_question,
)
from app.models.question import Question
from app.models.question_review import QuestionReviewItem, QuestionReviewResult

logger = logging.getLogger(__name__)


class QuestionReviewController:
    def __init__(self, *, min_confidence: float) -> None:
        self._min_confidence = min_confidence

    def collect(self, questions_dir: Path) -> QuestionReviewResult:
        """Load every question.json and flag steps worth a human look."""
        loaded, errors = load_question_artifacts(questions_dir)
        items = [
            QuestionReviewItem(
                path=path,
                question=question,
                flagged_steps=review_flags(question, min_confidence=self._min_confidence),
            )
            for path, question in loaded
        ]
        return QuestionReviewResult(questions_dir=Path(questions_dir), items=items, errors=errors)

    def require_valid(self, questions_dir: Path) -> QuestionReviewResult:
        """Collected questions, or ``QuestionArtifactsInvalidError`` if any fails to parse."""
        result = self.collect(questions_dir)
        if not result.ok:
            raise QuestionArtifactsInvalidError(result.errors)
        return result

    def save_question(self, questions_dir: Path, question: Question) -> QuestionReviewResult:
        """Persist one reviewed question; its LaTeX sidecar goes so student.tex follows the edit."""
        try:
            write_reviewed_question(questions_dir, question)
        except ValueError as exc:
            raise QuestionArtifactsInvalidError([str(exc)]) from exc
        drop_latex_sources(questions_dir, [question.question_id])
        return self.collect(questions_dir).model_copy(
            update={"edited_ids": [question.question_id]}
        )

    def prune_stale_latex_sources(self, questions_dir: Path) -> list[str]:
        """Drop sidecars of questions edited outside a run so student.tex follows the edit."""
        stale = stale_latex_sources(questions_dir)
        if stale:
            drop_latex_sources(questions_dir, stale)
            logger.info("LaTeX rebuilt for edited question(s): %s", ", ".join(stale))
        return stale
