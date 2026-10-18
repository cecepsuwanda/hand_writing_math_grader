"""Function topic pack (syllabus bab 3) — dual-track 50/50 symbolic + concept.

Isolated from other ChapterPacks: SOLUTION_SET finals, value_table, graph
endpoints, and a paid ``concept`` narrative bucket (LLM), without changing
bab 1.5/2 or ChapterPack defaults for bab 4–11.
"""

from __future__ import annotations

import re
from types import MappingProxyType

from app.capabilities.registry import ALL_CAPABILITY_IDS
from app.functions.score_aggregate import DEFAULT_PART_CRITERION_IDS
from app.models.exam_schema import ExamPart
from app.models.grading import Rubric, RubricCriterion
from app.models.recognition import SymbolicPayload
from app.models.validation import StepCheck
from app.topics.chapter_pack import RUBRIC_TOTAL, ChapterPack, MilestonePart

_FUNCTION3_CAPABILITY_IDS: tuple[str, ...] = ("piecewise",) + tuple(
    cid for cid in ALL_CAPABILITY_IDS if cid != "piecewise"
)

_DF_RE = re.compile(r"\bD_?\s*f\s*=", re.IGNORECASE)
_RF_RE = re.compile(r"\bR_?\s*f\s*=", re.IGNORECASE)
# Table points: numeric ``(x,y)`` or evaluated ``f(2)=…`` — not ``f(x)=…`` definitions.
_NUMERIC_PAIR_RE = re.compile(
    r"\(\s*[-+]?\d[\d.,/]*\s*,\s*[-+]?\d[\d.,/]*\s*\)",
)
_FX_EVAL_RE = re.compile(
    r"\bf\s*\(\s*(?!x\b)[^)]+\s*\)\s*=",
    re.IGNORECASE,
)
_FX_DEF_RE = re.compile(
    r"\bf\s*\(\s*x\s*\)\s*=",
    re.IGNORECASE,
)
_GRAPH_POINTS_RE = re.compile(r"GRAPH_POINTS\s*\(", re.IGNORECASE)
_NUMBER_LINE_RE = re.compile(r"NUMBER_LINE\s*\(", re.IGNORECASE)
_MATHISH_RE = re.compile(
    r"[=<>≤≥∈∪∘]|\\circ|\\leq|\\geq|\\in|\\cup|\\\\|f\s*\(|\\sqrt|\\mathbb",
    re.IGNORECASE,
)

SYMBOLIC_TOTAL = 5.0
CONCEPT_POINTS = 5.0
_FIGURE_RELATIVE = 2.0
_FINAL_RELATIVE = 2.0
_ALGEBRA_RELATIVE = 1.0


class Function3Pack(ChapterPack):
    """Bab 3 only — does not change default ChapterPack behaviour for bab 4–11."""

    domain_number_line_from_final = True
    figure_from_tikz = True
    grades_concept = True
    # Opt-in: prose + tabular + Domain/Range split + % concept / % value_table.
    rich_section_ingest = True
    part_criterion_ids = DEFAULT_PART_CRITERION_IDS | frozenset(
        {"domain", "range", "composition", "value_table", "concept"}
    )

    def __init__(self) -> None:
        super().__init__(
            pack_id="3",
            label="3 Fungsi",
            topik_refs=("3", "3.1", "3.2", "3.3", "3.4", "3.5"),
            milestones=(
                MilestonePart(
                    role="concept",
                    points=CONCEPT_POINTS,
                    titles=(
                        r"^Identifikasi\s+Jenis\s+Fungsi\b",
                        r"^Identifikasi\s+Setiap\s+Potongan\b",
                        r"^Periksa\s+Titik\s+Ujung\b",
                    ),
                    step_cue=(
                        r"\bradikan\b|\bmelompat\b|\bparabola\b|"
                        r"sehingga\s+radikan|jenis\s+fungsi|titik\s+(?:kosong|penuh)"
                    ),
                    check=StepCheck.NOT_SYMBOLIC,
                    hint=(
                        "conceptual narrative (why the radicand must be >= 0, "
                        "why the graph jumps, why composition exists or not); "
                        "put the explanation in raw_text and leave symbolic.repr "
                        "empty unless a formula is written"
                    ),
                ),
                MilestonePart(
                    role="domain",
                    points=1.0,
                    titles=(
                        r"^Domain\s+dan\s+Range\b",
                        r"^(?:Tentukan\s+)?Domain\b",
                    ),
                    step_cue=r"\bD_\s*\{?|\bdomain\b|daerah\s+asal",
                    check=StepCheck.SOLUTION_SET,
                    hint="the domain D_f (conditions such as radicand >= 0, the resulting interval)",
                ),
                MilestonePart(
                    role="range",
                    points=1.0,
                    titles=(r"^(?:Tentukan\s+)?Range\b",),
                    step_cue=r"\bR_\s*\{?|\brange\b|daerah\s+hasil",
                    check=StepCheck.SOLUTION_SET,
                    hint="the range R_f (minimum / maximum value, the resulting interval)",
                ),
                MilestonePart(
                    role="value_table",
                    points=1.0,
                    titles=(r"^Tabel\s+Nilai\b",),
                    step_cue=(
                        r"\btabel\s+nilai\b|"
                        r"\(\s*[-+]?\d[\d.,/]*\s*,\s*[-+]?\d[\d.,/]*\s*\)|"
                        r"f\s*\(\s*(?!x\b)[^)]+\s*\)\s*="
                    ),
                    check=StepCheck.TRANSITION,
                    hint=(
                        "a value table: numeric pairs (x, y) or f(a)=b used to "
                        "sketch the graph — not the definition f(x)=…"
                    ),
                ),
                MilestonePart(
                    role="composition",
                    points=1.0,
                    titles=(
                        r"^Bagian\s+\(a\),\s*Periksa\s+Syarat\b",
                        r"^Bagian\s+\(b\),\s*Rumus\b",
                        r"^Bagian\s+\(b\)\b",
                    ),
                    step_cue=r"\\circ|∘|\(\s*[fg]\s+o\s+[fg]\s*\)",
                    check=StepCheck.TRANSITION,
                    hint="a composition step: R_g ∩ D_f check or (f o g)(x) formula / value",
                ),
            ),
            figure_kinds=("number_line", "graph"),
            figure_from_tikz=True,
            figure_titles=(r"^Gambar(?:kan)?\s+Grafik\b",),
            algebra_hint="ordinary algebra (solve a condition, substitute, simplify)",
            final_hint=(
                "the requested answer (domain / range interval, composition "
                "formula or value; 'tidak ada')"
            ),
            capability_ids=_FUNCTION3_CAPABILITY_IDS,
        )
        self.step_checks = MappingProxyType(
            {
                **dict(self.step_checks),
                "concept": StepCheck.NOT_SYMBOLIC,
                "hp": StepCheck.SOLUTION_SET,
            }
        )
        self.role_rubric_parts = MappingProxyType(
            {
                **dict(self.role_rubric_parts),
                "concept": ("concept",),
            }
        )
        self.recognition_role_instructions = (
            self.recognition_role_instructions
            + '- Extra pack-3 roles: "concept" for prose explanations '
            "(raw_text only; do not invent equations); "
            '"domain" / "range" / "composition" as listed above; '
            '"value_table" only for numeric pairs (x,y) or f(a)=b — '
            'use "algebra" for the definition f(x)=…\n'
            "- Piecewise definitions: symbolic.repr = "
            "Piecewise((expr,cond),...) (ASCII); raw_text may keep "
            "\\begin{cases}.\n"
            "- Figure graphs: symbolic.repr = GRAPH_POINTS((x,y,open|closed);...) "
            "for labeled open/closed endpoints (not NUMBER_LINE).\n"
        )

    def rubric_from_parts(self, question_number: int, parts: list[ExamPart]) -> Rubric:
        """Dual-track: ``concept`` = 5; remaining symbolic criteria scale to 5."""
        kinds = {part.kind for part in parts}
        relative: dict[str, float] = {
            role: points
            for role, points in self._points.items()
            if role in kinds and role != "concept"
        }
        if "figure" in kinds:
            relative["figure"] = _FIGURE_RELATIVE
        if "hp" in kinds:
            relative["final_answer"] = _FINAL_RELATIVE
        if "algebra" in kinds or not relative:
            relative["algebra"] = relative.get("algebra", 0.0) + _ALGEBRA_RELATIVE

        total_rel = sum(relative.values()) or 1.0
        scale = SYMBOLIC_TOTAL / total_rel
        scaled = {
            cid: round(points * scale, 4) for cid, points in relative.items()
        }
        # Absorb rounding drift into algebra (or the last criterion).
        drift = round(SYMBOLIC_TOTAL - sum(scaled.values()), 4)
        if "algebra" in scaled:
            scaled["algebra"] = round(scaled["algebra"] + drift, 4)
        else:
            last = next(reversed(scaled))
            scaled[last] = round(scaled[last] + drift, 4)

        criteria = [
            RubricCriterion(id=cid, points=points)
            for cid, points in scaled.items()
            if points > 0
        ]
        criteria.append(RubricCriterion(id="concept", points=CONCEPT_POINTS))
        return Rubric(
            question=question_number,
            maximum_score=RUBRIC_TOTAL,
            criteria=criteria,
        )

    def coalesce_step_role(
        self,
        raw_text: str,
        symbolic: SymbolicPayload | None,
        role: str | None,
    ) -> str:
        if symbolic is not None and symbolic.kind == "figure":
            return "figure"
        blob = " ".join(
            part
            for part in (
                (raw_text or "").strip(),
                (symbolic.repr if symbolic else "") or "",
            )
            if part
        )
        if _GRAPH_POINTS_RE.search(blob) or _NUMBER_LINE_RE.search(blob):
            return "figure"
        # Prefer geometry of the ink over a mis-tagged recognition role.
        if _NUMERIC_PAIR_RE.search(blob) or _FX_EVAL_RE.search(blob):
            return "value_table"
        if _FX_DEF_RE.search(blob):
            return "algebra"
        normalized = role.strip().lower() if isinstance(role, str) else ""
        if normalized in self.roles and normalized != "algebra":
            return normalized
        if _DF_RE.search(blob) and not _RF_RE.search(blob):
            return "domain"
        if _RF_RE.search(blob):
            return "range"
        if blob and not _MATHISH_RE.search(blob) and len(blob) >= 12:
            return "concept"
        resolved = super().coalesce_step_role(raw_text, symbolic, role)
        if resolved == "algebra" and blob and not _MATHISH_RE.search(blob):
            return "concept"
        return resolved


PACK = Function3Pack()
