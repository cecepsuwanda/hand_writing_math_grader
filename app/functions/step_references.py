"""Map step roles to validation checks and pick each step's reference step (pure)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.models.validation import StepCheck


def step_checks_for(
    roles: Sequence[str | None],
    mapping: Mapping[str, StepCheck] | None,
) -> list[StepCheck]:
    """Check per step; missing roles and unmapped roles fall back to ``TRANSITION``.

    Roles are matched case- and whitespace-insensitively (hand-edited question.json).
    """
    table = {key.strip().lower(): check for key, check in (mapping or {}).items()}
    return [
        table.get(role.strip().lower(), StepCheck.TRANSITION) if role else StepCheck.TRANSITION
        for role in roles
    ]


def reference_indices(checks: Sequence[StepCheck]) -> list[int | None]:
    """Index of the step each step is checked against.

    Every step points at the latest earlier ``TRANSITION`` step, so role-specific
    steps (zero-makers, sign tests, solution sets) never chain off each other.
    Without role checks this is simply the previous step.
    """
    references: list[int | None] = []
    last_transition: int | None = None
    for index, check in enumerate(checks):
        references.append(last_transition)
        if check == StepCheck.TRANSITION:
            last_transition = index
    return references


def final_reference_index(checks: Sequence[StepCheck]) -> int | None:
    """Step the declared final answer is compared with.

    The last ``TRANSITION`` step when role-specific steps exist (the final answer
    must solve the reduced inequality), otherwise the last step.
    """
    if not checks:
        return None
    if all(check == StepCheck.TRANSITION for check in checks):
        return len(checks) - 1
    transitions = [i for i, check in enumerate(checks) if check == StepCheck.TRANSITION]
    return transitions[-1] if transitions else None
