"""Inequality 1.5 topic pack — HP, critical points, sign chart, number line."""

from __future__ import annotations

import re
from types import MappingProxyType

from app.models.exam_schema import ExamPart
from app.models.grading import Rubric, RubricCriterion
from app.models.recognition import SymbolicPayload
from app.models.validation import StepCheck

_RUBRIC_TOTAL = 10.0

_VALID_ROLES: frozenset[str] = frozenset(
    {"algebra", "critical_points", "sign_chart", "figure", "hp"}
)

_STEP_CHECKS = MappingProxyType(
    {
        "algebra": StepCheck.TRANSITION,
        "critical_points": StepCheck.ZERO_MAKERS,
        "sign_chart": StepCheck.NUMERIC_EVAL,
        "hp": StepCheck.SOLUTION_SET,
        "figure": StepCheck.NOT_SYMBOLIC,
    }
)

_HP_RE = re.compile(
    r"(?:^|\b(?:jadi|maka|sehingga|diperoleh)\s+)"
    r"(?:HP|himpunan\s+penyelesaian)\b",
    re.IGNORECASE,
)
_LEADIN_RE = re.compile(
    r"^\s*(?:jadi|maka|sehingga|diperoleh)\b\s*",
    re.IGNORECASE,
)
_PURE_INTERVAL_RE = re.compile(
    r"^\s*[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[\])]"
    r"(?:\s*(?:U|or|\\cup|∪)\s*[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[\])])*"
    r"\s*$",
    re.IGNORECASE,
)
_WHOLE_MEMBERSHIP_RE = re.compile(
    r"^\s*(?:(?:jadi|maka|sehingga|diperoleh)\s+)?"
    r"[A-Za-z][A-Za-z0-9_]*\s*(?:\\in|∈)\s*"
    r"[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[])](?:\s*(?:U|or|\\cup|∪)\s*"
    r"[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[])])*"
    r"\s*$",
    re.IGNORECASE,
)
_NUMBER_LINE_RE = re.compile(r"NUMBER_LINE\s*\(", re.IGNORECASE)
_CRITICAL_RE = re.compile(
    r"titik\s+(?:kritis|potong)|critical\s+points?|pembuat\s+nol",
    re.IGNORECASE,
)
_SIGN_RE = re.compile(
    r"analisis\s+tanda|sign\s+chart|uji\s+selang",
    re.IGNORECASE,
)
_FIGURE_RE = re.compile(
    r"garis\s+bilangan|number\s+line|\bdiagram\b|\bgraph\b|\bfigure\b",
    re.IGNORECASE,
)

# Full normalize chain (legacy math_normalize order) for MVP parity.
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

_ROLE_INSTRUCTIONS = """\
- Set "role" on every step:
  - "algebra" — ordinary transformations / equations
  - "critical_points" — roots / critical points / zero-makers
  - "sign_chart" — interval sign tests / analisis tanda
  - "figure" — number line / diagram (symbolic.kind must be "figure")
  - "hp" — final solution set / interval (Himpunan Penyelesaian). Use "hp"
    for the answer-set step even when the letters "HP" are not written
    (e.g. "Jadi (-1,1)", "x in (2,oo)", bare interval as the conclusion).
"""


def _blob(raw_text: str, symbolic: SymbolicPayload | None) -> str:
    return " ".join(
        part
        for part in (
            (raw_text or "").strip(),
            (symbolic.repr if symbolic is not None else "") or "",
        )
        if part
    )


def _strong_figure(raw_text: str, symbolic: SymbolicPayload | None) -> bool:
    if symbolic is not None and symbolic.kind == "figure":
        return True
    repr_text = (symbolic.repr if symbolic is not None else "") or ""
    if _NUMBER_LINE_RE.search(repr_text) or _NUMBER_LINE_RE.search(raw_text or ""):
        return True
    return bool(_FIGURE_RE.search(_blob(raw_text, symbolic)))


def _strong_hp(raw_text: str, symbolic: SymbolicPayload | None) -> bool:
    blob = _blob(raw_text, symbolic)
    return bool(blob and _HP_RE.search(blob))


def _weak_hp(raw_text: str, symbolic: SymbolicPayload | None) -> bool:
    raw = (raw_text or "").strip()
    repr_text = ((symbolic.repr if symbolic is not None else "") or "").strip()

    if raw and _PURE_INTERVAL_RE.match(raw):
        return True
    if repr_text and _PURE_INTERVAL_RE.match(repr_text):
        return True
    if raw and _WHOLE_MEMBERSHIP_RE.match(raw):
        return True
    if repr_text and _WHOLE_MEMBERSHIP_RE.match(repr_text):
        return True
    if raw:
        remainder = _LEADIN_RE.sub("", raw, count=1).strip()
        if remainder and remainder != raw and _PURE_INTERVAL_RE.match(remainder):
            return True
    return False


class Inequality15Pack:
    """Topic 1.5 — pertidaksamaan (bentuk umum + HP + garis bilangan)."""

    id = "1.5"
    label = "1.5 Pertidaksamaan (HP + garis bilangan)"
    topik_refs = ("1.5",)
    part_kinds = ("algebra", "critical_points", "sign_chart", "figure", "hp")
    roles = ("algebra", "critical_points", "sign_chart", "figure", "hp")
    step_checks = _STEP_CHECKS
    figure_kinds = ("number_line",)
    capability_ids = _CAPABILITY_IDS
    recognition_role_instructions = _ROLE_INSTRUCTIONS

    def rubric_from_parts(self, question_number: int, parts: list[ExamPart]) -> Rubric:
        kinds = {part.kind for part in parts}
        weights: dict[str, float] = {}
        if "algebra" in kinds:
            weights["algebra"] = 3.0
        if "critical_points" in kinds or "sign_chart" in kinds:
            weights["critical_points"] = 2.0
        if "figure" in kinds:
            weights["figure"] = 2.0
        if "hp" in kinds:
            weights["final_answer"] = 3.0

        total = sum(weights.values())
        if total <= 0:
            weights = {"algebra": 5.0, "final_answer": 5.0}
            total = _RUBRIC_TOTAL

        deficit = _RUBRIC_TOTAL - total
        if deficit > 0:
            has_algebra = "algebra" in weights
            has_final = "final_answer" in weights
            if has_algebra and has_final:
                half = deficit // 2
                weights["algebra"] += half
                weights["final_answer"] += deficit - half
            elif has_algebra:
                weights["algebra"] += deficit
            elif has_final:
                weights["final_answer"] += deficit
            else:
                weights["final_answer"] = deficit

        order = ("algebra", "critical_points", "figure", "final_answer")
        criteria = [
            RubricCriterion(id=cid, points=weights[cid])
            for cid in order
            if cid in weights
        ]
        for cid, points in weights.items():
            if cid not in order:
                criteria.append(RubricCriterion(id=cid, points=points))

        return Rubric(
            question=question_number,
            maximum_score=_RUBRIC_TOTAL,
            criteria=criteria,
        )

    def coalesce_step_role(
        self,
        raw_text: str,
        symbolic: SymbolicPayload | None,
        role: str | None,
    ) -> str:
        if _strong_figure(raw_text, symbolic):
            return "figure"
        if _strong_hp(raw_text, symbolic):
            return "hp"

        if isinstance(role, str):
            normalized = role.strip().lower()
            if normalized in _VALID_ROLES and normalized != "algebra":
                return normalized

        blob = _blob(raw_text, symbolic)
        if blob:
            if _CRITICAL_RE.search(blob):
                return "critical_points"
            if _SIGN_RE.search(blob):
                return "sign_chart"

        if _weak_hp(raw_text, symbolic):
            return "hp"
        return "algebra"


PACK = Inequality15Pack()
