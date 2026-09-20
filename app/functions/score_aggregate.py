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


def allocate_step_max_scores(rubric: Rubric, step_count: int) -> tuple[list[float], float]:
    """Split non-final criteria across steps; return (per_step_max, final_max)."""
    final_points = 0.0
    pool = 0.0
    for criterion in rubric.criteria:
        if criterion.id == "final_answer":
            final_points += criterion.points
        else:
            pool += criterion.points

    if step_count <= 0:
        return [], final_points

    per = pool / step_count
    scores = [round(per, 4) for _ in range(step_count)]
    # Fix rounding so sum matches pool
    diff = round(pool - sum(scores), 4)
    if scores:
        scores[-1] = round(scores[-1] + diff, 4)
    return scores, final_points


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
    next_validation: StepValidation | None,
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


def aggregate_question_grade(
    *,
    question_id: str,
    question_number: int,
    validation: QuestionValidation,
    rubric: Rubric,
) -> QuestionGrade:
    steps = sorted(validation.steps, key=lambda s: s.step_number)
    per_step_max, final_max = allocate_step_max_scores(rubric, len(steps))

    step_grades: list[StepGrade] = []
    review_required = False

    for index, step_val in enumerate(steps):
        maximum = per_step_max[index] if index < len(per_step_max) else 0.0
        fraction = score_fraction(step_val.status)
        earned = round(maximum * fraction, 4)
        if step_val.status == ValidationStatus.UNCERTAIN:
            review_required = True
        prev = steps[index - 1] if index > 0 else None
        nxt = steps[index + 1] if index + 1 < len(steps) else None
        error_type = infer_error_type(step_val, previous=prev, next_validation=nxt)
        # Carry-forward label on the *following* valid step after invalid
        if (
            step_val.status == ValidationStatus.VALID
            and prev is not None
            and prev.status == ValidationStatus.INVALID
        ):
            error_type = ErrorType.CARRY_FORWARD
        step_grades.append(
            StepGrade(
                step_number=step_val.step_number,
                score=earned,
                max_score=maximum,
                status=grade_status_for(step_val.status, earned, maximum),
                error_type=error_type,
                feedback=deterministic_feedback(step_val, error_type),
                validation_status=step_val.status,
            )
        )

    final_grade: StepGrade | None = None
    if validation.final_answer_status is not None:
        final_val = validation.final_answer_status
        fraction = score_fraction(final_val.status)
        earned = round(final_max * fraction, 4)
        if final_val.status == ValidationStatus.UNCERTAIN:
            review_required = True
        error_type = infer_error_type(final_val, previous=steps[-1] if steps else None, next_validation=None)
        final_grade = StepGrade(
            step_number=final_val.step_number,
            score=earned,
            max_score=final_max,
            status=grade_status_for(final_val.status, earned, final_max),
            error_type=error_type,
            feedback=deterministic_feedback(final_val, error_type),
            validation_status=final_val.status,
        )
    elif final_max > 0:
        # No final validation → no final points (not a zeroing of prior steps)
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
    )
