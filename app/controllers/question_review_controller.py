"""Human checkpoint: review extracted question.json before LaTeX / validation."""

from __future__ import annotations

from pathlib import Path

from app.exceptions import QuestionArtifactsInvalidError
from app.functions.question_review import review_flags
from app.functions.question_review_artifact import (
    drop_latex_sources,
    load_question_artifacts,
    question_fingerprints,
    stale_latex_sources,
)
from app.models.question_review import QuestionReviewItem, QuestionReviewResult
from app.views.prompt_view import InputFn, is_interactive
from app.views.question_review_view import (
    ask_transcription_ok,
    print_question_edits,
    print_question_review_summary,
    wait_for_question_edit,
)


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

    def prune_stale_latex_sources(self, questions_dir: Path) -> list[str]:
        """Drop sidecars of questions edited outside a run so student.tex follows the edit."""
        stale = stale_latex_sources(questions_dir)
        if stale:
            drop_latex_sources(questions_dir, stale)
            print_question_edits(stale)
        return stale

    def review_loop(
        self,
        questions_dir: Path,
        *,
        force_yes: bool = False,
        input_fn: InputFn | None = None,
    ) -> QuestionReviewResult:
        """Ask until transcription is OK and parseable; on no, wait for edit then reload."""
        if force_yes or not is_interactive(input_fn):
            result = self.collect(questions_dir)
            if not result.ok:
                raise QuestionArtifactsInvalidError(result.errors)
            return result
        before = question_fingerprints(questions_dir)
        while True:
            result = self.collect(questions_dir)
            print_question_review_summary(result)
            if result.ok and ask_transcription_ok(input_fn=input_fn):
                break
            edited = wait_for_question_edit(questions_dir=Path(questions_dir), input_fn=input_fn)
            if not edited and not result.ok:
                raise QuestionArtifactsInvalidError(result.errors)
        return self._finish(questions_dir, result, before)

    @staticmethod
    def _finish(
        questions_dir: Path,
        result: QuestionReviewResult,
        before: dict[str, str],
    ) -> QuestionReviewResult:
        after = question_fingerprints(questions_dir)
        edited = sorted(qid for qid, digest in after.items() if before.get(qid) != digest)
        if not edited:
            return result
        drop_latex_sources(questions_dir, edited)
        print_question_edits(edited)
        return result.model_copy(update={"edited_ids": edited})
