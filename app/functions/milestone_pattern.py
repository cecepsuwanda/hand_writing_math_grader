"""Build kunci langkah pattern slots for Review / Results (pure FP)."""

from __future__ import annotations

from app.models.exam_schema import ExamMilestone, ExamQuestion
from app.models.question_review import ExpectedMilestoneSlot

_SKIP_ROLES = frozenset({"hp"})
_SUMMARY_MAX = 120


def summary_from_milestone(milestone: ExamMilestone) -> str:
    """Short preview of milestone atoms / latex for the UX checklist."""
    atoms = [
        (step or "").strip()
        for step in (milestone.steps or [])
        if (step or "").strip()
    ]
    if atoms:
        blob = " ; ".join(atoms[:2])
    else:
        blob = (milestone.latex or "").strip()
    blob = " ".join(blob.split())
    if len(blob) <= _SUMMARY_MAX:
        return blob
    return blob[: _SUMMARY_MAX - 1].rstrip() + "…"


def build_expected_milestones(exam_q: ExamQuestion | None) -> list[ExpectedMilestoneSlot]:
    """Ordered kunci pattern slots; empty when schema question missing."""
    if exam_q is None:
        return []
    slots: list[ExpectedMilestoneSlot] = []
    order = 0
    for milestone in exam_q.milestones or []:
        role = (milestone.role or "").strip().lower()
        if not role or role in _SKIP_ROLES:
            continue
        title = (milestone.title or "").strip()
        slots.append(
            ExpectedMilestoneSlot(
                role=role,
                title=title or role,
                summary=summary_from_milestone(milestone),
                order=order,
            )
        )
        order += 1
    if exam_q.expects_figure and not any(s.role == "figure" for s in slots):
        slots.append(
            ExpectedMilestoneSlot(
                role="figure",
                title="Gambar / grafik",
                summary="",
                order=order,
            )
        )
    return slots
