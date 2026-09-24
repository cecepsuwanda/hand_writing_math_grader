"""Monotonic soft-align of student steps to standard solution rows."""

from __future__ import annotations

from collections.abc import Sequence

from app.models.validation import ValidationStatus

AlignResult = dict[int, tuple[ValidationStatus, str]]


def align_student_steps_to_standard(
    student_rows: Sequence[tuple[int, Sequence[bool | None] | None]],
    *,
    skip_reasons: dict[int, str] | None = None,
    default_skip_reason: str = "figure step skipped for standard align",
) -> AlignResult:
    """Greedy monotonic soft-align via pairwise equivalence.

    Each entry is ``(student_step_number, equivalence_row)``.
    ``equivalence_row[j]`` is ``True`` / ``False`` / ``None`` vs standard
    step ``j`` (0-based).  A ``None`` row means the student step cannot be
    compared (e.g. figure): ``UNCERTAIN`` without consuming a standard slot.

    Preference per student step among remaining standards (``j >= cursor``):
    1. first ``True`` → ``VALID``, advance cursor past ``j``
    2. else first ``None`` → ``UNCERTAIN``, advance cursor past ``j``
    3. else ``INVALID`` (no match); cursor unchanged
    """
    reasons = skip_reasons or {}
    results: AlignResult = {}
    cursor = 0

    for step_number, row in student_rows:
        if row is None:
            results[step_number] = (
                ValidationStatus.UNCERTAIN,
                reasons.get(step_number, default_skip_reason),
            )
            continue

        n_std = len(row)
        true_j: int | None = None
        uncertain_j: int | None = None
        for j in range(cursor, n_std):
            eq = row[j]
            if eq is True and true_j is None:
                true_j = j
                break
            if eq is None and uncertain_j is None:
                uncertain_j = j

        if true_j is not None:
            results[step_number] = (
                ValidationStatus.VALID,
                f"step matches standard step {true_j + 1}",
            )
            cursor = true_j + 1
            continue

        if uncertain_j is not None:
            results[step_number] = (
                ValidationStatus.UNCERTAIN,
                f"SymPy could not decide vs standard step {uncertain_j + 1}",
            )
            cursor = uncertain_j + 1
            continue

        results[step_number] = (
            ValidationStatus.INVALID,
            "no matching standard step",
        )

    return results
