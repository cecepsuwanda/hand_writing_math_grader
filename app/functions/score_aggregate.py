"""Pure scoring: map validation statuses + rubric → question grade."""

from __future__ import annotations

from app.models.grading import (
    ErrorType,
    QuestionGrade,
    ReviewStatus,
    Rubric,
    StepGrade,
    StepGradeStatus,
)
from app.models.validation import QuestionValidation, StepValidation, ValidationStatus

# Rubric ids scored outside the per-step algebra pool.
_PART_CRITERION_IDS = frozenset({"critical_points", "figure", "final_answer"})


def allocate_step_max_scores(
    rubric: Rubric,
    step_count: int,
) -> tuple[list[float], float, dict[str, float]]:
    """Split algebra pool across steps; return (per_step_max, final_max, part_max).

    ``part_max`` holds points for ``critical_points`` / ``figure`` (and any
    other reserved part ids except ``final_answer``, which is ``final_max``).
    """
    final_points = 0.0
    pool = 0.0
    part_max: dict[str, float] = {}
    for criterion in rubric.criteria:
        if criterion.id == "final_answer":
            final_points += criterion.points
        elif criterion.id in _PART_CRITERION_IDS:
            part_max[criterion.id] = (
                part_max.get(criterion.id, 0.0) + criterion.points
            )
        else:
            # algebra and legacy ids (setup/transformation/…) → step pool
            pool += criterion.points

    if step_count <= 0:
        return [], final_points, part_max

    per = pool / step_count
    scores = [round(per, 4) for _ in range(step_count)]
    if scores:
        diff = round(pool - sum(scores), 4)
        scores[-1] = round(scores[-1] + diff, 4)
    return scores, final_points, part_max


def score_fraction(status: ValidationStatus) -> float:
    if status == ValidationStatus.VALID:
        return 1.0
    if status == ValidationStatus.UNCERTAIN:
        return 0.5
    return 0.0


def grade_status_for(validation_status: ValidationStatus, earned: float, maximum: float) -> StepGradeStatus:
    if validation_status == ValidationStatus.UNCERTAIN:
        return StepGradeStatus.REVIEW
    if maximum <= 0:
        return StepGradeStatus.CORRECT
    if earned <= 0:
        return StepGradeStatus.INCORRECT
    if earned + 1e-9 >= maximum:
        return StepGradeStatus.CORRECT
    return StepGradeStatus.PARTIAL


def infer_error_type(
    validation: StepValidation,
    *,
    previous: StepValidation | None,
) -> ErrorType:
    if validation.status == ValidationStatus.VALID:
        if (
            previous is not None
            and previous.status == ValidationStatus.INVALID
        ):
            return ErrorType.CARRY_FORWARD
        return ErrorType.NONE
    if validation.status == ValidationStatus.UNCERTAIN:
        return ErrorType.UNCERTAIN
    # invalid
    if "parse" in (validation.reason or "").lower():
        return ErrorType.TRANSCRIPTION
    return ErrorType.CALCULATION


def deterministic_feedback(validation: StepValidation, error_type: ErrorType) -> str:
    base = validation.reason or validation.status.value
    if error_type == ErrorType.CARRY_FORWARD:
        return f"{base}; consistent with a prior error (carry-forward)"
    if error_type == ErrorType.UNCERTAIN:
        return f"{base}; marked for human review"
    return base


def _part_mark(
    entry: tuple,
) -> tuple[ValidationStatus, str, float | None]:
    """Unpack ``(status, reason)`` or ``(status, reason, fraction)``."""
    status = entry[0]
    reason = str(entry[1])
    if len(entry) >= 3 and entry[2] is not None:
        return status, reason, float(entry[2])
    return status, reason, None


def _part_step_grade(
    *,
    part_id: str,
    maximum: float,
    status: ValidationStatus,
    reason: str,
    fraction: float | None = None,
) -> StepGrade:
    earned_fraction = (
        score_fraction(status) if fraction is None else min(1.0, max(0.0, fraction))
    )
    earned = round(maximum * earned_fraction, 4)
    return StepGrade(
        step_number=0,
        score=earned,
        max_score=maximum,
        status=grade_status_for(status, earned, maximum),
        error_type=(
            ErrorType.UNCERTAIN
            if status == ValidationStatus.UNCERTAIN
            else ErrorType.NONE
        ),
        feedback=f"part:{part_id}; {reason}",
        validation_status=status,
    )


def aggregate_question_grade(
    *,
    question_id: str,
    question_number: int,
    validation: QuestionValidation,
    rubric: Rubric,
    standard_final_status: ValidationStatus | None = None,
    standard_final_reason: str = "",
    standard_step_results: dict[int, tuple[ValidationStatus, str]] | None = None,
    part_statuses: dict[str, tuple] | None = None,
) -> QuestionGrade:
    steps = sorted(validation.steps, key=lambda s: s.step_number)
    per_step_max, final_max, part_max = allocate_step_max_scores(
        rubric, len(steps)
    )

    step_grades: list[StepGrade] = []
    review_required = False
    audit_steps: dict[str, str] = {}

    for index, step_val in enumerate(steps):
        maximum = per_step_max[index] if index < len(per_step_max) else 0.0
        consistency_fraction = score_fraction(step_val.status)
        if step_val.status == ValidationStatus.UNCERTAIN:
            review_required = True

        # Soft-align to the key is audit/feedback only; step score is
        # consistency alone so alternate valid paths are not zeroed.
        fraction = consistency_fraction
        label_status = step_val.status
        std_reason = ""
        if standard_step_results is not None:
            std_entry = standard_step_results.get(step_val.step_number)
            if std_entry is not None:
                std_status, std_reason = std_entry
                audit_steps[str(step_val.step_number)] = std_status.value
            else:
                std_reason = "no matching standard step"
                audit_steps[str(step_val.step_number)] = (
                    ValidationStatus.INVALID.value
                )

        earned = round(maximum * fraction, 4)
        prev = steps[index - 1] if index > 0 else None
        error_type = infer_error_type(step_val, previous=prev)
        feedback = deterministic_feedback(step_val, error_type)
        if standard_step_results is not None and std_reason:
            feedback = f"{feedback}; standard: {std_reason}"

        step_grades.append(
            StepGrade(
                step_number=step_val.step_number,
                score=earned,
                max_score=maximum,
                status=grade_status_for(label_status, earned, maximum),
                error_type=error_type,
                feedback=feedback,
                validation_status=step_val.status,
            )
        )

    parts = part_statuses or {}
    recorded_part_statuses: dict[str, str] = {}
    for part_id, maximum in part_max.items():
        if maximum <= 0:
            continue
        fraction: float | None = None
        if part_id in parts:
            status, reason, fraction = _part_mark(parts[part_id])
        else:
            status, reason = (
                ValidationStatus.INVALID,
                f"no {part_id} evidence",
            )
        recorded_part_statuses[part_id] = status.value
        if status == ValidationStatus.UNCERTAIN:
            review_required = True
        step_grades.append(
            _part_step_grade(
                part_id=part_id,
                maximum=maximum,
                status=status,
                reason=reason,
                fraction=fraction,
            )
        )

    final_grade: StepGrade | None = None
    consistency = validation.final_answer_status
    if consistency is not None or standard_final_status is not None:
        if consistency is not None:
            consistency_fraction = score_fraction(consistency.status)
            if consistency.status == ValidationStatus.UNCERTAIN:
                review_required = True
        else:
            # No student-side consistency check: do not invent a full score.
            # Score from standard alone when present.
            consistency_fraction = None

        if standard_final_status is not None:
            standard_fraction = score_fraction(standard_final_status)
            if standard_final_status == ValidationStatus.UNCERTAIN:
                review_required = True
            if consistency_fraction is None:
                fraction = standard_fraction
                label_status = standard_final_status
            else:
                fraction = min(consistency_fraction, standard_fraction)
                label_status = (
                    standard_final_status
                    if standard_fraction <= consistency_fraction
                    else consistency.status  # type: ignore[union-attr]
                )
        else:
            assert consistency is not None and consistency_fraction is not None
            fraction = consistency_fraction
            label_status = consistency.status

        earned = round(final_max * fraction, 4)

        if consistency is not None:
            error_type = infer_error_type(
                consistency, previous=steps[-1] if steps else None
            )
            base_feedback = deterministic_feedback(consistency, error_type)
            step_number = consistency.step_number
            reported_status = consistency.status
        else:
            error_type = ErrorType.NONE
            base_feedback = (
                "no consistency final-answer validation; "
                "scored from standard compare only"
            )
            step_number = 0
            reported_status = standard_final_status or ValidationStatus.INVALID

        if standard_final_status is not None and standard_final_reason:
            feedback = f"{base_feedback}; standard: {standard_final_reason}"
        else:
            feedback = base_feedback

        final_grade = StepGrade(
            step_number=step_number,
            score=earned,
            max_score=final_max,
            status=grade_status_for(label_status, earned, final_max),
            error_type=error_type,
            feedback=feedback,
            validation_status=reported_status,
        )
    elif final_max > 0:
        final_grade = StepGrade(
            step_number=0,
            score=0.0,
            max_score=final_max,
            status=StepGradeStatus.INCORRECT,
            error_type=ErrorType.NONE,
            feedback="no final-answer validation available",
            validation_status=ValidationStatus.INVALID,
        )

    total = sum(s.score for s in step_grades)
    if final_grade is not None:
        total += final_grade.score
    total = min(round(total, 4), rubric.maximum_score)

    return QuestionGrade(
        question_id=question_id,
        question_number=question_number,
        score=total,
        maximum_score=rubric.maximum_score,
        steps=step_grades,
        final_answer=final_grade,
        review_status=(
            ReviewStatus.REVIEW_REQUIRED
            if review_required
            else ReviewStatus.AUTO_ACCEPT
        ),
        standard_final_status=standard_final_status,
        standard_step_statuses=audit_steps or None,
        part_statuses=recorded_part_statuses or None,
    )
