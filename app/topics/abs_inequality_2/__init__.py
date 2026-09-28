"""Absolute-value inequality pack (syllabus bab 2) — reuses 1.5 roles/rubric."""

from __future__ import annotations

from app.models.exam_schema import ExamPart
from app.models.grading import Rubric
from app.models.recognition import SymbolicPayload
from app.topics.inequality_1_5 import PACK as INEQUALITY_15

# Abs-first chain; keep interval/HP support and shared symbolic adapters.
_CAPABILITY_IDS: tuple[str, ...] = (
    "matrix",
    "det_inverse",
    "vector",
    "abs",
    "interval",
    "limit",
    "derivative",
    "integral",
    "transcendental",
)


class AbsInequalityPack:
    """Topic 2 — pertidaksamaan nilai mutlak (slice)."""

    id = "2"
    label = "2 Pertidaksamaan nilai mutlak"
    topik_refs = ("2", "2.1", "2.2")
    part_kinds = INEQUALITY_15.part_kinds
    roles = INEQUALITY_15.roles
    # Figure optional via kunci expects_figure; not required by pack.
    figure_kinds = ("number_line", "none")
    capability_ids = _CAPABILITY_IDS
    recognition_role_instructions = INEQUALITY_15.recognition_role_instructions

    def rubric_from_parts(self, question_number: int, parts: list[ExamPart]) -> Rubric:
        return INEQUALITY_15.rubric_from_parts(question_number, parts)

    def coalesce_step_role(
        self,
        raw_text: str,
        symbolic: SymbolicPayload | None,
        role: str | None,
    ) -> str:
        return INEQUALITY_15.coalesce_step_role(raw_text, symbolic, role)


PACK = AbsInequalityPack()
