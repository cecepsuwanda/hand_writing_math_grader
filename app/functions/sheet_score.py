"""Sheet rubric for one topic: 100 points per butir, exam total = mean.

Pack 3 installs this. Other packs leave the arguments unset and keep
per-step fractions and a summed total.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.functions.question_names import question_dir_name
from app.functions.score_aggregate import grade_status_for, score_fraction
from app.models.grading import QuestionGrade, ReviewStatus, StepGrade, StepGradeStatus
from app.models.question import Question
from app.models.report import (
    MISSING_UNANSWERED,
    MISSING_UNGRADED,
    QuestionReportRow,
)
from app.models.validation import ValidationStatus

SHEET_MAXIMUM = 100.0
LANGKAH_FLOOR = 25.0

QuestionKey = tuple[int, str]
_EXCLUDED_LANGKAH_ROLES = frozenset({"figure", "hp"})


@dataclass(frozen=True)
class SheetButir:
    """One row of the nilai sheet. ``members`` are the graded sub-soal keys."""

    question_number: int
    part_label: str
    members: tuple[QuestionKey, ...]
    langkah: float
    jawaban: float
    penyajian: float

    @property
    def maximum(self) -> float:
        return self.langkah + self.jawaban + self.penyajian


@dataclass(frozen=True)
class SheetScorePolicy:
    """How one sub-soal is scored before butir rollup.

    ``apply_floor`` is off for a member of a merged butir: the floor of 25 is
    applied once to the combined langkah, not to each half.
    """

    langkah: float
    jawaban: float
    penyajian: float
    apply_floor: bool
    floor: float = LANGKAH_FLOOR


def question_is_readable(question: Question) -> bool:
    """A transcribed step with text counts as readable work."""
    for step in question.student_steps:
        if (step.raw_text or "").strip() or (step.latex or "").strip():
            return True
        if step.symbolic is not None and (step.symbolic.repr or "").strip():
            return True
    return False


def apply_sheet_policy(
    grade: QuestionGrade,
    policy: SheetScorePolicy,
    *,
    milestone_marks: Mapping[str, tuple] | None = None,
    readable: bool = False,
) -> QuestionGrade:
    """Snap jawaban and penyajian to 0 or full, then score langkah as one pool."""
    steps = [_snap_figure(step, policy.penyajian) for step in grade.steps]
    fraction, statuses = _langkah_signals(grade.steps, milestone_marks or {})
    langkah = round(fraction * policy.langkah, 4)
    entirely_invalid = not statuses or all(
        status == ValidationStatus.INVALID for status in statuses
    )
    if (
        policy.apply_floor
        and readable
        and not entirely_invalid
    ):
        langkah = max(langkah, min(policy.floor, policy.langkah))
    langkah = min(langkah, policy.langkah)
    steps = _pay_langkah(steps, langkah)
    final, review = _snap_jawaban(grade, policy.jawaban)
    if review:
        review_status = ReviewStatus.REVIEW_REQUIRED
    else:
        review_status = grade.review_status
    part_statuses = dict(grade.part_statuses or {})
    part_statuses["algebra"] = _pool_status(langkah, policy.langkah, statuses)
    figure = next((step for step in steps if step.part_id == "figure"), None)
    if figure is not None:
        part_statuses["figure"] = _pool_status(
            figure.score, figure.max_score, (figure.validation_status,)
        )
    total = sum(step.score for step in steps)
    if final is not None:
        total += final.score
    maximum = round(policy.langkah + policy.jawaban + policy.penyajian, 4)
    return grade.model_copy(
        update={
            "steps": steps,
            "final_answer": final,
            "score": min(round(total, 4), maximum),
            "maximum_score": maximum,
            "review_status": review_status,
            "part_statuses": part_statuses or None,
        }
    )


def sheet_report_rows(
    grades: Sequence[QuestionGrade],
    butir_list: Sequence[SheetButir],
    *,
    readable: Mapping[QuestionKey, bool] | None = None,
    missing_labels: Mapping[QuestionKey, str] | None = None,
    floor: float = LANGKAH_FLOOR,
) -> list[QuestionReportRow]:
    """One row per butir. A merged butir (4a+4b, …) is a single 100-point row.

    A butir with no graded member is 0 and still counts toward the mean.
    """
    by_key = {(grade.question_number, grade.part_label): grade for grade in grades}
    readable = readable or {}
    missing_labels = missing_labels or {}
    rows: list[QuestionReportRow] = []
    for butir in butir_list:
        present = [by_key[key] for key in butir.members if key in by_key]
        anchor = butir.members[0]
        if not present:
            rows.append(
                QuestionReportRow(
                    question_id=question_dir_name(*anchor),
                    question_number=butir.question_number,
                    part_label=butir.part_label,
                    score=0.0,
                    maximum_score=butir.maximum,
                    review_status=ReviewStatus.REVIEW_REQUIRED,
                    missing=True,
                    missing_label=_missing_label(butir.members, missing_labels),
                )
            )
            continue
        if len(butir.members) == 1:
            grade = present[0]
            rows.append(
                QuestionReportRow(
                    question_id=grade.question_id,
                    question_number=butir.question_number,
                    part_label=butir.part_label,
                    score=grade.score,
                    maximum_score=grade.maximum_score,
                    review_status=grade.review_status,
                    step_count=sum(1 for step in grade.steps if step.step_number > 0),
                    part_statuses=dict(grade.part_statuses or {}),
                )
            )
            continue
        rows.append(_merged_row(butir, present, readable, floor))
    return rows


def _merged_row(
    butir: SheetButir,
    present: Sequence[QuestionGrade],
    readable: Mapping[QuestionKey, bool],
    floor: float,
) -> QuestionReportRow:
    by_key = {(grade.question_number, grade.part_label): grade for grade in present}
    fractions: list[float] = []
    any_readable = False
    any_credit = False
    for key in butir.members:
        grade = by_key.get(key)
        if grade is None:
            fractions.append(0.0)
            continue
        if readable.get(key, False):
            any_readable = True
        earned, maximum, credited = _langkah_earned(grade)
        if credited:
            any_credit = True
        fractions.append(earned / maximum if maximum > 0 else 0.0)
    langkah = round((sum(fractions) / len(butir.members)) * butir.langkah, 4)
    if any_readable and any_credit:
        langkah = max(langkah, min(floor, butir.langkah))
    langkah = min(langkah, butir.langkah)
    jawaban_full = all(_jawaban_is_full(by_key.get(key), butir.jawaban) for key in butir.members)
    jawaban = butir.jawaban if jawaban_full else 0.0
    review = ReviewStatus.AUTO_ACCEPT
    if any(
        grade.review_status == ReviewStatus.REVIEW_REQUIRED
        or grade.standard_final_status == ValidationStatus.UNCERTAIN
        for grade in present
    ):
        review = ReviewStatus.REVIEW_REQUIRED
    statuses = {
        "algebra": _pool_status(langkah, butir.langkah, ()),
        "final_answer": "valid" if jawaban_full else "invalid",
    }
    return QuestionReportRow(
        question_id=question_dir_name(*butir.members[0]),
        question_number=butir.question_number,
        part_label=butir.part_label,
        score=round(langkah + jawaban, 4),
        maximum_score=butir.maximum,
        review_status=review,
        step_count=sum(1 for grade in present for step in grade.steps if step.step_number > 0),
        part_statuses=statuses,
    )


def _langkah_earned(grade: QuestionGrade) -> tuple[float, float, bool]:
    """``(earned, maximum, credited)`` for the langkah pool already on the grade."""
    steps = [
        step
        for step in grade.steps
        if step.part_id != "figure" and step.step_number > 0 and step.max_score > 0
    ]
    earned = round(sum(step.score for step in steps), 4)
    maximum = round(sum(step.max_score for step in steps), 4)
    credited = any(step.validation_status != ValidationStatus.INVALID for step in steps)
    return earned, maximum, credited


def _jawaban_is_full(grade: QuestionGrade | None, jawaban_max: float) -> bool:
    if grade is None or grade.standard_final_status != ValidationStatus.VALID:
        return False
    final = grade.final_answer
    if final is None or jawaban_max <= 0:
        return False
    return final.score + 1e-9 >= jawaban_max


def _missing_label(members: Sequence[QuestionKey], labels: Mapping[QuestionKey, str]) -> str:
    values = [labels.get(member) for member in members]
    if any(value == MISSING_UNGRADED for value in values):
        return MISSING_UNGRADED
    return MISSING_UNANSWERED


def _langkah_signals(
    steps: Sequence[StepGrade],
    milestone_marks: Mapping[str, tuple],
) -> tuple[float, list[ValidationStatus]]:
    fractions: list[float] = []
    statuses: list[ValidationStatus] = []
    for step in steps:
        if step.part_id is not None or step.step_number <= 0 or step.max_score <= 0:
            continue
        fractions.append(score_fraction(step.validation_status))
        statuses.append(step.validation_status)
    for role, mark in milestone_marks.items():
        if role in _EXCLUDED_LANGKAH_ROLES or not mark:
            continue
        status = mark[0]
        if not isinstance(status, ValidationStatus):
            continue
        fraction = mark[2] if len(mark) >= 3 and mark[2] is not None else None
        fractions.append(score_fraction(status) if fraction is None else float(fraction))
        statuses.append(status)
    if not fractions:
        return 0.0, statuses
    return sum(fractions) / len(fractions), statuses


def _pay_langkah(steps: list[StepGrade], target: float) -> list[StepGrade]:
    """Spread ``target`` across the langkah steps, never past each step's max."""
    indexes = [
        index
        for index, step in enumerate(steps)
        if step.part_id is None and step.step_number > 0 and step.max_score > 0
    ]
    if not indexes:
        if target <= 1e-9:
            return steps
        paid = StepGrade(
            step_number=0,
            score=round(target, 4),
            max_score=round(target, 4),
            status=StepGradeStatus.PARTIAL,
            validation_status=ValidationStatus.VALID,
            part_id="algebra",
        )
        return [*steps, paid]
    weights = [score_fraction(steps[index].validation_status) for index in indexes]
    if sum(weights) <= 1e-12:
        weights = [1.0] * len(indexes)
    weight_sum = sum(weights)
    desired = [target * weight / weight_sum for weight in weights]
    paid = [min(amount, steps[indexes[i]].max_score) for i, amount in enumerate(desired)]
    leftover = target - sum(paid)
    if leftover > 1e-9:
        for offset, index in enumerate(indexes):
            room = steps[index].max_score - paid[offset]
            if room <= 1e-9:
                continue
            take = min(room, leftover)
            paid[offset] += take
            leftover -= take
            if leftover <= 1e-9:
                break
    drift = round(target - sum(paid), 4)
    if indexes and abs(drift) > 1e-9:
        last = len(indexes) - 1
        room = steps[indexes[last]].max_score - paid[last]
        paid[last] = round(paid[last] + min(drift, max(room, 0.0)), 4)
    updated = list(steps)
    for offset, index in enumerate(indexes):
        step = steps[index]
        score = round(paid[offset], 4)
        updated[index] = step.model_copy(
            update={
                "score": score,
                "status": grade_status_for(step.validation_status, score, step.max_score),
            }
        )
    return updated


def _snap_figure(step: StepGrade, penyajian: float) -> StepGrade:
    if step.part_id != "figure":
        return step
    full = (
        step.validation_status == ValidationStatus.VALID
        and step.max_score > 0
        and step.score + 1e-9 >= step.max_score
    )
    score = penyajian if full else 0.0
    maximum = penyajian if penyajian > 0 else step.max_score
    return step.model_copy(
        update={
            "score": score,
            "max_score": maximum,
            "status": grade_status_for(step.validation_status, score, maximum),
        }
    )


def _snap_jawaban(
    grade: QuestionGrade, jawaban: float
) -> tuple[StepGrade | None, bool]:
    """Key status ``VALID`` pays the whole jawaban column. Anything else pays 0."""
    final = grade.final_answer
    status = grade.standard_final_status
    if final is None and status is None:
        return None, False
    full = status == ValidationStatus.VALID
    score = jawaban if full else 0.0
    label = (
        final.validation_status
        if final is not None
        else (status or ValidationStatus.INVALID)
    )
    review = label == ValidationStatus.UNCERTAIN or status == ValidationStatus.UNCERTAIN
    base = final or StepGrade(
        step_number=0,
        score=0.0,
        max_score=jawaban,
        status=StepGradeStatus.INCORRECT,
        validation_status=label,
    )
    snapped = base.model_copy(
        update={
            "score": score,
            "max_score": jawaban,
            "status": grade_status_for(label, score, jawaban),
            "validation_status": label,
        }
    )
    return snapped, review


def _pool_status(
    earned: float,
    maximum: float,
    statuses: Sequence[ValidationStatus],
) -> str:
    if maximum > 0 and earned + 1e-9 >= maximum:
        return ValidationStatus.VALID.value
    if any(status == ValidationStatus.UNCERTAIN for status in statuses):
        return ValidationStatus.UNCERTAIN.value
    if earned <= 1e-9:
        return ValidationStatus.INVALID.value
    return "partial"
