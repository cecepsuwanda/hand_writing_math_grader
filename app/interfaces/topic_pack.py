"""Topic pack contract — per-syllabus grading/ingest/role vocabulary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.models.exam_schema import ExamPart
from app.models.grading import Rubric
from app.models.recognition import SymbolicPayload
from app.models.validation import StepCheck


@runtime_checkable
class TopicPack(Protocol):
    """User-selectable topic pack (bab / fokus silabus)."""

    @property
    def id(self) -> str:
        """Stable pack id (e.g. ``1.5``)."""

    @property
    def label(self) -> str:
        """Human-readable menu label."""

    @property
    def topik_refs(self) -> tuple[str, ...]:
        """Syllabus references in ``docs/math-topics.md`` (e.g. ``(\"1.5\",)``)."""

    @property
    def part_kinds(self) -> tuple[str, ...]:
        """Allowed exam part kinds for this pack."""

    @property
    def roles(self) -> tuple[str, ...]:
        """Allowed step / milestone roles."""

    @property
    def step_checks(self) -> Mapping[str, StepCheck]:
        """Step role → validation check; unmapped roles use ``TRANSITION``."""

    @property
    def role_rubric_parts(self) -> Mapping[str, str]:
        """Step role → rubric part id that scores it (outside the algebra pool)."""

    @property
    def figure_kinds(self) -> tuple[str, ...]:
        """Figure kinds this pack grades (e.g. ``number_line``, ``none``)."""

    @property
    def capability_ids(self) -> tuple[str, ...]:
        """Normalize/check capabilities activated for this pack."""

    @property
    def recognition_role_instructions(self) -> str:
        """Optional crop_math role hint block (empty if unused)."""

    def rubric_from_parts(self, question_number: int, parts: list[ExamPart]) -> Rubric:
        """Build a rubric from exam parts for this pack."""

    def coalesce_step_role(
        self,
        raw_text: str,
        symbolic: SymbolicPayload | None,
        role: str | None,
    ) -> str:
        """Infer a concrete step role for recognition → grading."""
