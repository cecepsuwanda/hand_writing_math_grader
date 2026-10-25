"""Pure helpers for the web results page (part labels, dual-track split)."""

from __future__ import annotations

from types import MappingProxyType

from app.models.grading import QuestionGrade, StepGrade

PART_DISPLAY_LABELS: MappingProxyType[str, str] = MappingProxyType(
    {
        "algebra": "Aljabar",
        "concept": "Konsep",
        "domain": "Domain",
        "range": "Range",
        "value_table": "Tabel nilai",
        "composition": "Komposisi",
        "figure": "Gambar",
        "final_answer": "Jawaban akhir",
        "critical_points": "Titik kritis",
        "sign_chart": "Tabel tanda",
        "hp": "HP",
    }
)

_CONCEPT_PART = "concept"


def part_labels_for(pack: object) -> dict[str, str]:
    """Base labels, with a pack overlay (topik 3: Langkah / Jawaban / Penyajian)."""
    labels = dict(PART_DISPLAY_LABELS)
    overlay = getattr(pack, "sheet_part_labels", None)
    if overlay:
        labels.update(overlay)
    return labels


def display_part_label(part_id: str) -> str:
    key = (part_id or "").strip()
    return PART_DISPLAY_LABELS.get(key, key or "—")


def figures_section_heading(figure_kinds: tuple[str, ...] | list[str]) -> str:
    """LaTeX report paragraph title for OCR figures."""
    kinds = {k.lower() for k in figure_kinds}
    if "graph" in kinds:
        return "Gambar / grafik (OCR)"
    if "number_line" in kinds:
        return "Gambar / garis bilangan (OCR)"
    return "Gambar (OCR)"


def split_grade_rows(
    grade: QuestionGrade | None,
) -> tuple[list[StepGrade], list[StepGrade]]:
    """Student steps (numbered) vs rubric part rows (``part_id``)."""
    if grade is None:
        return [], []
    steps = [s for s in grade.steps if s.step_number > 0]
    parts = [s for s in grade.steps if s.part_id]
    if not parts:
        parts = [s for s in grade.steps if s.step_number == 0]
    return steps, parts


def dual_track_scores(
    grade: QuestionGrade | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """``(concept_score, concept_max, symbolic_score, symbolic_max)`` or Nones."""
    if grade is None:
        return None, None, None, None
    concept_rows = [s for s in grade.steps if (s.part_id or "") == _CONCEPT_PART]
    if not concept_rows:
        return None, None, None, None
    concept_score = round(sum(s.score for s in concept_rows), 4)
    concept_max = round(sum(s.max_score for s in concept_rows), 4) or 5.0
    symbolic_score = round(grade.score - concept_score, 4)
    symbolic_max = round(grade.maximum_score - concept_max, 4)
    if symbolic_max < 0:
        symbolic_max = 0.0
    return concept_score, concept_max, symbolic_score, symbolic_max
