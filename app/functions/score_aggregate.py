"""Pure scoring: map validation statuses + rubric → question grade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.functions.step_references import is_recovered
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
_PART_CRITERION_IDS = frozenset(
    {"critical_points", "sign_chart", "figure", "final_answer"}
)
# Algebra pool when every step is already scored under another rubric part.
ALGEBRA_POOL_PART = "algebra"

# Machine-readable feedback tails. The feedback annotator rewrites the human
# part of a feedback string, so it carries these through verbatim; both sides
# read the markers from here so they cannot drift apart.
_STANDARD_MARKER = "; standard: "
_PART_MARKER = "; scored under part:"
# Marks a final answer that the key scored although the student's own chain
# disagreed. This is a decision record, so the annotator leaves the wording of
# such a row alone rather than paraphrasing the score away.
KEY_OVERRIDE_MARKER = "; key override: "
KEY_OVERRIDE_NOTE = (
    "final answer matches the key, so it is scored from the key and marked "
    "for human review"
)


def split_feedback_markers(feedback: str) -> tuple[str, str]:
    """Split ``text; standard: …; scored under part:…`` into (text, markers)."""
    index = len(feedback)
    for marker in (_STANDARD_MARKER, _PART_MARKER, KEY_OVERRIDE_MARKER):
        found = feedback.find(marker)
        if found != -1:
            index = min(index, found)
    return feedback[:index], feedback[index:]


def allocate_step_max_scores(
    rubric: Rubric,
    step_count: int,
    part_steps: Sequence[bool] | None = None,
) -> tuple[list[float], float, dict[str, float]]:
    """Split algebra pool across steps; return (per_step_max, final_max, part_max).

    ``part_max`` holds points for ``critical_points`` / ``figure`` (and any
    other reserved part ids except ``final_answer``, which is ``final_max``).
    ``part_steps[i]`` marks a step already scored by a rubric part: it gets
    max 0. When every step is marked there is no algebra step to carry the
    pool, so it moves to ``part_max["algebra"]`` (judged for review instead of
    paying the same steps twice).
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

    flags = list(part_steps or [])[:step_count]
    flags += [False] * (step_count - len(flags))
    if all(flags):
        if pool > 0:
            part_max[ALGEBRA_POOL_PART] = part_max.get(ALGEBRA_POOL_PART, 0.0) + pool
        return [0.0] * step_count, final_points, part_max
    receivers = [i for i, flagged in enumerate(flags) if not flagged]
    per = pool / len(receivers)
    scores = [0.0 if flagged else round(per, 4) for flagged in flags]
    diff = round(pool - sum(scores), 4)
    scores[receivers[-1]] = round(scores[receivers[-1]] + diff, 4)
    return scores, final_points, part_max


def _part_buckets(rubric: Rubric) -> set[str]:
    """Rubric ids that can hold points (a zero-point id scores nothing)."""
    return {criterion.id for criterion in rubric.criteria if criterion.points > 0}


def _resolve_part_bucket(
    role: str,
    present: set[str],
    role_rubric_parts: Mapping[str, Sequence[str]],
) -> str | None:
    """First bucket the rubric grants ``role``; ``None`` means the algebra pool.

    A role lists its candidate buckets in order. Rubrics ingested before
    ``sign_chart`` became its own bucket define only ``critical_points``, so the
    ``sign_chart`` role still resolves there and keeps its old score.
    """
    for candidate in role_rubric_parts.get(role) or ():
        if candidate in present:
            return candidate
    return None


def part_step_flags(
    rubric: Rubric,
    step_numbers: Sequence[int],
    step_roles: Mapping[int, str | None] | None,
    role_rubric_parts: Mapping[str, Sequence[str]] | None,
) -> list[str | None]:
    """Rubric part id that already scores each step (``None`` = algebra pool)."""
    if not step_roles or not role_rubric_parts:
        return [None] * len(step_numbers)
    present = _part_buckets(rubric)
    return [
        _resolve_part_bucket(step_roles.get(number) or "", present, role_rubric_parts)
        for number in step_numbers
    ]


def _mark_fraction(mark: tuple) -> float:
    fraction = mark[2]
    if fraction is not None:
        return float(fraction)
    return score_fraction(mark[0])


def _average_marks(left: tuple, right: tuple) -> tuple[ValidationStatus, str, float | None]:
    """Mean of two marks that share one rubric bucket (both must contribute)."""
    mean = (_mark_fraction(left) + _mark_fraction(right)) / 2
    undecided = (
        left[0] == ValidationStatus.UNCERTAIN or right[0] == ValidationStatus.UNCERTAIN
    )
    reason = f"{left[1]}; {right[1]}"
    if mean >= 1.0 - 1e-9:
        return ValidationStatus.VALID, reason, 1.0
    if undecided and left[2] is None and right[2] is None and mean <= 0.5 + 1e-9:
        return ValidationStatus.UNCERTAIN, reason, None
    if mean <= 1e-9:
        return ValidationStatus.INVALID, reason, 0.0
    if undecided:
        return ValidationStatus.UNCERTAIN, reason, mean
    return ValidationStatus.INVALID, reason, mean


def fold_role_marks(
    marks: Mapping[str, tuple],
    rubric: Rubric,
    role_rubric_parts: Mapping[str, Sequence[str]] | None,
) -> dict[str, tuple[ValidationStatus, str, float | None]]:
    """Fold milestone marks (keyed by role) into the rubric's part buckets.

    Marks are keyed by milestone role, but scoring is keyed by rubric id. When a
    rubric gives ``critical_points`` and ``sign_chart`` their own buckets each
    keeps its own score; when it predates that split both roles resolve to
    ``critical_points`` and are averaged exactly as they were before.
    """
    if not marks or not role_rubric_parts:
        return {}
    present = _part_buckets(rubric)
    grouped: dict[str, list[tuple]] = {}
    for role, mark in marks.items():
        bucket = _resolve_part_bucket(role, present, role_rubric_parts)
        if bucket is not None:
            grouped.setdefault(bucket, []).append(mark)
    folded: dict[str, tuple[ValidationStatus, str, float | None]] = {}
    for bucket, bucket_marks in grouped.items():
        combined = bucket_marks[0]
        for mark in bucket_marks[1:]:
            combined = _average_marks(combined, mark)
        folded[bucket] = combined
    return folded


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
        if validation_status == ValidationStatus.INVALID:
            return StepGradeStatus.INCORRECT
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
            and not is_recovered(validation.reason)
        ):
            return ErrorType.CARRY_FORWARD
        return ErrorType.NONE
    if validation.status == ValidationStatus.UNCERTAIN:
        return ErrorType.UNCERTAIN
    # invalid
    if "parse" in (validation.reason or "").lower():
        return ErrorType.TRANSCRIPTION
    return ErrorType.CALCULATION


def _step_before(
    steps: Sequence[StepValidation], step_number: int
) -> StepValidation | None:
    """Step preceding the one numbered ``step_number``; the last step if absent."""
    for index, step in enumerate(steps):
        if step.step_number == step_number:
            return steps[index - 1] if index > 0 else None
    return steps[-1] if steps else None


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
        part_id=part_id,
    )


def _apply_step_override(
    step: StepValidation,
    override: tuple[ValidationStatus, str] | None,
) -> StepValidation:
    if (
        override is None
        or step.status != ValidationStatus.VALID
        or override[0] != ValidationStatus.UNCERTAIN
    ):
        return step
    return step.model_copy(
        update={
            "status": ValidationStatus.UNCERTAIN,
            "reason": f"{step.reason}; {override[1]}" if step.reason else override[1],
        }
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
    step_overrides: dict[int, tuple[ValidationStatus, str]] | None = None,
    step_roles: Mapping[int, str | None] | None = None,
    role_rubric_parts: Mapping[str, Sequence[str]] | None = None,
) -> QuestionGrade:
    """``step_overrides`` may only downgrade a VALID step to UNCERTAIN (never raise a score).

    Steps whose role maps (via ``role_rubric_parts``) to a part present in the
    rubric get no share of the algebra pool; that part scores them instead.
    """
    steps = [
        _apply_step_override(step, (step_overrides or {}).get(step.step_number))
        for step in sorted(validation.steps, key=lambda s: s.step_number)
    ]
    scored_under = part_step_flags(
        rubric, [s.step_number for s in steps], step_roles, role_rubric_parts
    )
    per_step_max, final_max, part_max = allocate_step_max_scores(
        rubric, len(steps), [part_id is not None for part_id in scored_under]
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
                std_reason = "not aligned to the standard"

        earned = round(maximum * fraction, 4)
        prev = steps[index - 1] if index > 0 else None
        error_type = infer_error_type(step_val, previous=prev)
        feedback = deterministic_feedback(step_val, error_type)
        if standard_step_results is not None and std_reason:
            feedback = f"{feedback}{_STANDARD_MARKER}{std_reason}"
        if scored_under[index] is not None and maximum <= 0:
            feedback = f"{feedback}{_PART_MARKER}{scored_under[index]}"

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
        part_fraction: float | None = None
        if part_id in parts:
            status, reason, part_fraction = _part_mark(parts[part_id])
        elif part_id == ALGEBRA_POOL_PART:
            status, reason = (
                ValidationStatus.UNCERTAIN,
                "no algebra steps; all steps scored under rubric parts",
            )
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
                fraction=part_fraction,
            )
        )

    final_grade: StepGrade | None = None
    consistency = validation.final_answer_status
    if consistency is not None or standard_final_status is not None:
        final_consistency: float | None = None
        if consistency is not None:
            final_consistency = score_fraction(consistency.status)
            if consistency.status == ValidationStatus.UNCERTAIN:
                review_required = True
        # Without a student-side consistency check, do not invent a full score:
        # score from the standard alone when present.

        key_overrides_chain = False
        if standard_final_status is not None:
            standard_fraction = score_fraction(standard_final_status)
            if standard_final_status == ValidationStatus.UNCERTAIN:
                review_required = True
            if consistency is None or final_consistency is None:
                fraction = standard_fraction
                label_status = standard_final_status
            elif (
                standard_final_status == ValidationStatus.VALID
                and standard_fraction > final_consistency
            ):
                # The key matches but the student's own chain disagrees. Zeroing
                # a final answer that matches the key punishes one bad link
                # mid-chain, so pay from the key and hand the disagreement to a
                # human instead of displaying a correct answer as 0.
                fraction = standard_fraction
                label_status = ValidationStatus.UNCERTAIN
                key_overrides_chain = True
                review_required = True
            elif final_consistency < standard_fraction:
                fraction = final_consistency
                label_status = consistency.status
            else:
                fraction = standard_fraction
                label_status = standard_final_status
        else:
            assert consistency is not None and final_consistency is not None
            fraction = final_consistency
            label_status = consistency.status

        earned = round(final_max * fraction, 4)

        if consistency is not None:
            error_type = infer_error_type(
                consistency,
                previous=_step_before(steps, consistency.step_number),
            )
            base_feedback = deterministic_feedback(consistency, error_type)
            step_number = consistency.step_number
            reported_status = consistency.status
            if key_overrides_chain:
                error_type = ErrorType.UNCERTAIN
                reported_status = standard_final_status or ValidationStatus.VALID
                base_feedback = (
                    f"{consistency.reason or consistency.status.value}"
                    f"{KEY_OVERRIDE_MARKER}{KEY_OVERRIDE_NOTE}"
                )
        else:
            error_type = ErrorType.NONE
            base_feedback = (
                "no consistency final-answer validation; "
                "scored from standard compare only"
            )
            step_number = 0
            reported_status = standard_final_status or ValidationStatus.INVALID

        if standard_final_status is not None and standard_final_reason:
            feedback = f"{base_feedback}{_STANDARD_MARKER}{standard_final_reason}"
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
