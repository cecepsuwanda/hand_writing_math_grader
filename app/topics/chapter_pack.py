"""Data-driven topic pack for syllabus chapters graded as equality chains.

A chapter pack only declares its milestone parts (kunci section titles, step
text cues, rubric points); roles, step checks, rubric and role coalescing are
derived here so every chapter behaves the same way.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from app.capabilities.registry import ALL_CAPABILITY_IDS
from app.functions.kunci_finals import extract_conclusion_value
from app.models.exam_schema import ExamPart
from app.models.grading import Rubric, RubricCriterion
from app.models.recognition import SymbolicPayload
from app.models.validation import StepCheck

RUBRIC_TOTAL = 10.0
FINAL_ANSWER_POINTS = 3.0

_CONCLUSION_RE = re.compile(
    r"^\s*(?:jadi|maka|sehingga|diperoleh|kesimpulan)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class MilestonePart:
    """One graded milestone of a chapter (role = part kind = rubric criterion id)."""

    role: str
    points: float
    # Kunci section titles (``Langkah N:`` already dropped), matched at the start.
    titles: tuple[str, ...]
    # Student step text / symbolic repr that marks this role (searched).
    step_cue: str | None = None
    check: StepCheck = StepCheck.TRANSITION
    hint: str = ""


class ChapterPack:
    """``TopicPack`` built from ``MilestonePart`` declarations."""

    def __init__(
        self,
        *,
        pack_id: str,
        label: str,
        topik_refs: tuple[str, ...],
        milestones: Sequence[MilestonePart],
        algebra_hint: str,
        final_hint: str,
        figure_kinds: tuple[str, ...] = ("none",),
        figure_from_tikz: bool = False,
        figure_titles: tuple[str, ...] = (),
        extract_final: Callable[[str], str | None] = extract_conclusion_value,
        capability_ids: tuple[str, ...] = ALL_CAPABILITY_IDS,
    ) -> None:
        self.id = pack_id
        self.label = label
        self.topik_refs = topik_refs
        self._milestones = tuple(milestones)
        self.figure_kinds = figure_kinds
        self.figure_from_tikz = figure_from_tikz
        self.capability_ids = capability_ids
        self._extract_final = extract_final

        milestone_roles = tuple(m.role for m in self._milestones)
        draws = "none" not in figure_kinds or figure_from_tikz or bool(figure_titles)
        self.part_kinds = (
            ("algebra",) + milestone_roles + (("figure",) if draws else ()) + ("hp",)
        )
        self.roles = ("algebra",) + milestone_roles + ("figure", "hp")
        self.step_checks: Mapping[str, StepCheck] = MappingProxyType(
            {
                "algebra": StepCheck.TRANSITION,
                **{m.role: m.check for m in self._milestones},
                "figure": StepCheck.NOT_SYMBOLIC,
                "hp": StepCheck.TRANSITION,
            }
        )
        self.role_rubric_parts: Mapping[str, Sequence[str]] = MappingProxyType(
            {
                **{m.role: (m.role,) for m in self._milestones},
                "figure": ("figure",),
                "hp": ("final_answer",),
            }
        )
        self.ingest_section_roles: tuple[tuple[str, str], ...] = tuple(
            (title, m.role) for m in self._milestones for title in m.titles
        ) + tuple((title, "figure") for title in figure_titles)
        self._step_cues = tuple(
            (re.compile(m.step_cue, re.IGNORECASE), m.role)
            for m in self._milestones
            if m.step_cue
        )
        self._points = {m.role: m.points for m in self._milestones}
        lines = [
            '- Set "role" on every step:',
            f'  - "algebra" — {algebra_hint}',
            *(f'  - "{m.role}" — {m.hint}' for m in self._milestones if m.hint),
            '  - "figure" — a sketch / graph (symbolic.kind must be "figure")',
            f'  - "hp" — {final_hint}',
        ]
        self.recognition_role_instructions = "\n".join(lines) + "\n"

    def extract_final(self, answer_tex: str) -> str | None:
        return self._extract_final(answer_tex)

    def rubric_from_parts(self, question_number: int, parts: list[ExamPart]) -> Rubric:
        """Milestones keep their points, ``final_answer`` 3; ``algebra`` takes the rest."""
        kinds = {part.kind for part in parts}
        weights = {role: points for role, points in self._points.items() if role in kinds}
        if "figure" in kinds:
            weights["figure"] = 2.0
        if "hp" in kinds:
            weights["final_answer"] = FINAL_ANSWER_POINTS
        remainder = RUBRIC_TOTAL - sum(weights.values())
        criteria: list[RubricCriterion] = []
        if "algebra" in kinds or not weights:
            criteria.append(RubricCriterion(id="algebra", points=remainder))
        else:
            weights[next(reversed(weights))] += remainder
        criteria.extend(RubricCriterion(id=cid, points=points) for cid, points in weights.items())
        return Rubric(question=question_number, maximum_score=RUBRIC_TOTAL, criteria=criteria)

    def coalesce_step_role(
        self,
        raw_text: str,
        symbolic: SymbolicPayload | None,
        role: str | None,
    ) -> str:
        if symbolic is not None and symbolic.kind == "figure":
            return "figure"
        normalized = role.strip().lower() if isinstance(role, str) else ""
        if normalized in self.roles and normalized != "algebra":
            return normalized
        if _CONCLUSION_RE.match(raw_text or ""):
            return "hp"
        blob = " ".join(
            part
            for part in ((raw_text or "").strip(), (symbolic.repr if symbolic else "") or "")
            if part
        )
        for pattern, cue_role in self._step_cues:
            if pattern.search(blob):
                return cue_role
        return "algebra"
