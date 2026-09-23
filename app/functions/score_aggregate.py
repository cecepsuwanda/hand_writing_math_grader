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


def allocate_step_max_scores(
    rubric: Rubric,
    step_count: int,
    *,
    expected_step_count: int | None = None,
) -> tuple[list[float], float]:
    """Split non-final criteria across steps; return (per_step_max, final_max).

    When ``expected_step_count`` is larger than observed steps, the pool is
    divided by the expected count so incomplete solutions cannot earn the
    entire step pool from a single valid fragment.
    """
    final_points = 0.0
    pool = 0.0
    for criterion in rubric.criteria:
        if criterion.id == "final_answer":
            final_points += criterion.points
        else:
            pool += criterion.points

    if step_count <= 0:
        return [], final_points

    slots = max(step_count, expected_step_count or 0)
    per = pool / slots
    scores = [round(per, 4) for _ in range(step_count)]
    # Fix rounding so awarded step maxes stay consistent; leftover stays unearned
    # when expected_step_count > step_count.
    if slots == step_count and scores:
        diff = round(pool - sum(scores), 4)
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
    standard_final_status: ValidationStatus | None = None,
    standard_final_reason: str = "",
    standard_step_results: dict[int, tuple[ValidationStatus, str]] | None = None,
    expected_step_count: int | None = None,
) -> QuestionGrade:
    steps = sorted(validation.steps, key=lambda s: s.step_number)
    per_step_max, final_max = allocate_step_max_scores(
        rubric,
        len(steps),
        expected_step_count=expected_step_count,
    )

    step_grades: list[StepGrade] = []
    review_required = False
    audit_steps: dict[str, str] = {}

    for index, step_val in enumerate(steps):
        maximum = per_step_max[index] if index < len(per_step_max) else 0.0
        consistency_fraction = score_fraction(step_val.status)
        if step_val.status == ValidationStatus.UNCERTAIN:
            review_required = True

        std_entry = None
        if standard_step_results:
            std_entry = standard_step_results.get(step_val.step_number)
            if std_entry is None:
                # A partial align map means this step has no standard row.
                # Do not award consistency-only credit for the gap.
                std_entry = (
                    ValidationStatus.INVALID,
                    "no matching standard step",
                )
            std_status, std_reason = std_entry
            audit_steps[str(step_val.step_number)] = std_status.value
            std_fraction = score_fraction(std_status)
            if std_status == ValidationStatus.UNCERTAIN:
                review_required = True
            fraction = min(consistency_fraction, std_fraction)
            label_status = (
                std_status
                if std_fraction <= consistency_fraction
                else step_val.status
            )
        else:
            fraction = consistency_fraction
            label_status = step_val.status
            std_reason = ""

        earned = round(maximum * fraction, 4)
        prev = steps[index - 1] if index > 0 else None
        error_type = infer_error_type(step_val, previous=prev)
        feedback = deterministic_feedback(step_val, error_type)
        if std_entry is not None and std_reason:
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
    )
