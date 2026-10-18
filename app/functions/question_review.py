"""Flag transcribed steps that deserve a human look (pure)."""

from __future__ import annotations

from collections.abc import Mapping

from app.models.question import Question, StudentStep
from app.models.question_review import ReviewFlag, StepReviewFlags
from app.models.validation import StepCheck

_UNCERTAIN_MARK = "[uncertain"
_FIGURE_KIND = "figure"


def _step_flags(
    step: StudentStep,
    min_confidence: float,
    step_checks: Mapping[str, StepCheck] | None,
) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    if step.confidence is not None and step.confidence < min_confidence:
        flags.append(ReviewFlag.LOW_CONFIDENCE)
    if _UNCERTAIN_MARK in (step.raw_text or "").lower():
        flags.append(ReviewFlag.UNCERTAIN_MARK)
    symbolic = step.symbolic
    role = (step.role or "").strip().lower()
    is_figure = role == _FIGURE_KIND or (
        symbolic is not None and symbolic.kind == _FIGURE_KIND
    )
    check = step_checks.get(role) if step_checks and role else None
    allow_empty_symbolic = is_figure or check == StepCheck.NOT_SYMBOLIC
    if not allow_empty_symbolic and not (
        symbolic is not None and (symbolic.repr or "").strip()
    ):
        flags.append(ReviewFlag.MISSING_SYMBOLIC)
    return flags


def review_flags(
    question: Question,
    *,
    min_confidence: float,
    step_checks: Mapping[str, StepCheck] | None = None,
) -> list[StepReviewFlags]:
    """Steps with at least one flag, in step order."""
    flagged: list[StepReviewFlags] = []
    for step in sorted(question.student_steps, key=lambda s: s.step_number):
        flags = _step_flags(step, min_confidence, step_checks)
        if flags:
            flagged.append(StepReviewFlags(step_number=step.step_number, flags=flags))
    return flagged
