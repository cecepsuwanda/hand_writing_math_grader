"""View-side assertions: compact checks on results and rendered CLI text."""
from __future__ import annotations

from app.models.validation import QuestionValidation, ValidationStatus


def assert_step_statuses(result: QuestionValidation, *expected: ValidationStatus) -> None:
    assert [s.status for s in result.steps] == list(expected)


def assert_all_valid(result: QuestionValidation) -> None:
    """Every step and the final answer validated VALID."""
    assert result.steps
    assert_step_statuses(result, *[ValidationStatus.VALID] * len(result.steps))
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def assert_contains(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"missing {missing!r} in output:\n{text}"
