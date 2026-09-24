"""Pure helpers to ingest kunci_jawaban TeX into standards solution files."""

from __future__ import annotations

import re
from pathlib import Path

from app.functions.standard_extract import (
    exam_schema_path,
    extract_solution_steps_from_tex,
)
from app.functions.number_line import number_line_from_symbolic, number_line_to_repr
from app.functions.symbolic_from_latex import latex_to_symbolic_payload
from app.models.exam_schema import (
    ExamMethod,
    ExamMilestone,
    ExamPart,
    ExamQuestion,
    ExamSchema,
)
from app.models.grading import Rubric, RubricCriterion

_ENUMERATE_BODY_RE = re.compile(
    r"\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}",
    re.DOTALL | re.IGNORECASE,
)

# Top-level soal items start with math ($... or \displaystyle)
_QUESTION_ITEM_SPLIT_RE = re.compile(
    r"(?=\\item\s+(?:\$|\\displaystyle))",
)

_QUESTION_ITEM_START_RE = re.compile(
    r"^\\item\s+(?:\$|\\displaystyle)",
)

# Stem = math after \item until solution body starts
_STEM_RE = re.compile(
    r"^\\item\s+(?P<stem>.+?)"
    r"(?=\\textbf\s*\{\s*Penyelesaian\s*:?\s*\}|\\begin\s*\{\s*itemize\s*\}|$)",
    re.DOTALL | re.IGNORECASE,
)

_TEX_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

_HP_RE = re.compile(
    r"HP:\s*\$(?P<hp>.+?)\$",
    re.IGNORECASE | re.DOTALL,
)

_QUAD_TEXT_RE = re.compile(
    r"\\quad\s*\\text\{(?:[^{}]|\{[^{}]*\})*\}",
)

_TIKZ_RE = re.compile(r"\\begin\s*\{\s*tikzpicture\s*\}", re.IGNORECASE)

_ITEMIZE_BODY_RE = re.compile(
    r"\\begin\{itemize\}(?P<body>.*?)\\end\{itemize\}",
    re.DOTALL | re.IGNORECASE,
)

_ITEMIZE_ITEM_SPLIT_RE = re.compile(r"(?=\\item\b)")

_METHOD_TITLE_RE = re.compile(
    r"^Metode\s+(?P<n>\d+)\s*:\s*(?P<label>.+)$",
    re.IGNORECASE,
)
_SIGN_TITLE_RE = re.compile(r"^Analisis\s+Tanda\b", re.IGNORECASE)
_CRITICAL_TITLE_RE = re.compile(
    r"^(?:Tentukan\s+)?Titik\s+(?:Potong|Kritis)\b",
    re.IGNORECASE,
)
_FIGURE_TITLE_RE = re.compile(r"^Gambar\s+Garis\b", re.IGNORECASE)
_HP_TITLE_RE = re.compile(r"^HP\s*:", re.IGNORECASE)
_LANGKAH_TITLE_RE = re.compile(r"^Langkah", re.IGNORECASE)

_SOAL_MARKER_RE = re.compile(
    r"%\s*soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_GAMBAR_MARKER_RE = re.compile(
    r"%\s*gambar\s+soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_SOAL_BLOCK_SPLIT_RE = re.compile(
    r"(?=%\s*soal\s+ke\s+\d+\b)",
    re.IGNORECASE,
)

_NO_EXAM_KEY = (
    "(no exam key provided; infer question_number from handwriting if visible)"
)

_METHOD_LABEL_IDS: dict[str, str] = {
    "pemaktoran": "factoring",
    "rumus abc": "quadratic_formula",
    "abc": "quadratic_formula",
}

_RUBRIC_TOTAL = 10.0


def extract_soal_number(item_tex: str) -> int | None:
    """Return ``N`` from ``% soal ke N`` if present."""
    match = _SOAL_MARKER_RE.search(item_tex)
    if match is None:
        return None
    return int(match.group("n"))


def item_has_gambar_marker(item_tex: str) -> bool:
    """True if ``% gambar soal ke N`` appears in the block."""
    return _GAMBAR_MARKER_RE.search(item_tex) is not None


def split_enumerate_items(tex: str) -> list[str]:
    """Return outer enumerate question blocks (math-led ``\\item`` only).

    When ``% soal ke N`` markers exist, split on those markers so each block
    keeps its soal/jawaban/gambar comments.
    """
    match = _ENUMERATE_BODY_RE.search(tex)
    if match is None:
        return []
    body = match.group("body")
    if _SOAL_MARKER_RE.search(body):
        chunks = _SOAL_BLOCK_SPLIT_RE.split(body)
        items: list[str] = []
        for chunk in chunks:
            cleaned = chunk.strip()
            if not cleaned:
                continue
            if _SOAL_MARKER_RE.search(cleaned) and (
                _QUESTION_ITEM_START_RE.search(cleaned)
                or "\\item" in cleaned
            ):
                items.append(cleaned)
        if items:
            return items

    chunks = _QUESTION_ITEM_SPLIT_RE.split(body)
    items = []
    for chunk in chunks:
        cleaned = chunk.strip()
        if not cleaned:
            continue
        if _QUESTION_ITEM_START_RE.match(cleaned):
            items.append(cleaned)
    return items


def _clean_align_steps(raw_steps: list[str]) -> list[str]:
    steps: list[str] = []
    for step in raw_steps:
        cleaned = _QUAD_TEXT_RE.sub("", step)
        cleaned = " ".join(cleaned.split())
        if cleaned:
            steps.append(cleaned)
    return steps


def extract_align_steps(item_tex: str) -> list[str]:
    """Extract align/aligned rows from one question block; strip ``\\quad\\text``."""
    return _clean_align_steps(extract_solution_steps_from_tex(item_tex))


def extract_hp_final(item_tex: str) -> str | None:
    """Return HP math from ``HP: $...$``, or None."""
    match = _HP_RE.search(item_tex)
    if match is None:
        return None
    hp = match.group("hp").strip()
    hp = " ".join(hp.split())
    return hp or None


def _itemize_sections(item_tex: str) -> list[tuple[str, str]]:
    """Return ``(title, body)`` for each ``\\item`` in the first itemize."""
    match = _ITEMIZE_BODY_RE.search(item_tex)
    if match is None:
        return []
    body = match.group("body")
    sections: list[tuple[str, str]] = []
    for chunk in _ITEMIZE_ITEM_SPLIT_RE.split(body):
        cleaned = chunk.strip()
        if not cleaned.lower().startswith("\\item"):
            continue
        content = cleaned[5:].lstrip()  # drop \item
        # Title = first non-empty line (comments stripped)
        lines = content.splitlines()
        title = ""
        body_start = 0
        for index, line in enumerate(lines):
            stripped = _TEX_COMMENT_RE.sub("", line).strip()
            if not stripped:
                continue
            title = stripped
            body_start = index + 1
            break
        rest = "\n".join(lines[body_start:])
        sections.append((title, rest if rest.strip() else content))
    return sections


def _method_id_from_label(label: str, method_number: int) -> str:
    key = " ".join(label.lower().split())
    if key in _METHOD_LABEL_IDS:
        return _METHOD_LABEL_IDS[key]
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return slug or f"method_{method_number}"


def _symbolic_steps(steps: list[str]) -> list:
    return [latex_to_symbolic_payload(step) for step in steps]


def _append_aligned_block(lines: list[str], steps: list[str]) -> None:
    if not steps:
        return
    lines.append(r"\begin{aligned}")
    for index, step in enumerate(steps):
        suffix = r" \\" if index < len(steps) - 1 else ""
        lines.append(f"{step}{suffix}")
    lines.append(r"\end{aligned}")
    lines.append("")


def render_standard_solution_tex(
    steps: list[str] | None = None,
    final: str = "",
    *,
    source_note: str = "",
    question: ExamQuestion | None = None,
) -> str:
    """Build standards-format solution TeX (tagged methods + ``% final answer``)."""
    header = "% Ingested from kunci_jawaban"
    if source_note:
        header = f"{header} ({source_note})"
    lines = [header]

    if question is not None:
        shared = list(question.steps)
        if shared:
            lines.append("% shared")
            _append_aligned_block(lines, shared)
        for method in question.methods:
            lines.append(f"% method: {method.id}")
            _append_aligned_block(lines, method.steps)
        for milestone in question.milestones:
            if milestone.role == "hp":
                continue
            lines.append(f"% role: {milestone.role}")
            if milestone.steps:
                _append_aligned_block(lines, milestone.steps)
            elif (milestone.latex or "").strip():
                lines.append(f"% {milestone.latex.strip()}")
                lines.append("")
        if question.expects_figure:
            lines.append("% role: figure")
            if question.number_line is not None and question.number_line.intervals:
                lines.append(
                    f"% number_line: {number_line_to_repr(question.number_line)}"
                )
            lines.append("")
        final_text = (question.final or final or "").strip()
    else:
        shared = list(steps or [])
        if shared:
            lines.append("% shared")
            _append_aligned_block(lines, shared)
        final_text = (final or "").strip()

    lines.append("% final answer")
    lines.append(final_text)
    lines.append("")
    return "\n".join(lines)


def rubric_from_parts(question_number: int, parts: list[ExamPart]) -> Rubric:
    """Build a 10-point rubric from exam parts (topic 1.5 defaults)."""
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

    # Prefer stable criterion order.
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


def extract_question_stem(item_tex: str) -> str | None:
    """Return the problem stem (math after ``\\item``), excluding solution body."""
    match = _STEM_RE.match(item_tex.strip())
    if match is None:
        return None
    stem = match.group("stem")
    stem = _TEX_COMMENT_RE.sub("", stem)
    stem = " ".join(stem.split())
    return stem or None


def extract_question_stems(tex: str) -> list[tuple[int, str]]:
    """Parse kunci TeX into ``(question_number, stem)`` pairs (1-based).

    Stems are problem statements only — never align steps or HP.
    Honors ``% soal ke N`` when present.
    """
    results: list[tuple[int, str]] = []
    for index, item in enumerate(split_enumerate_items(tex), start=1):
        question = build_exam_question(index, item)
        if question is None:
            continue
        results.append((question.number, question.stem))
    return results


def load_question_stems_from_kunci(path_or_dir: Path | str) -> list[tuple[int, str]]:
    """Load stems from a kunci ``.tex`` file or the first ``.tex`` in a directory.

    Returns ``[]`` if the path is missing, empty, or has no parseable stems.
    """
    path = Path(path_or_dir)
    if not path.exists():
        return []
    if path.is_dir():
        tex_files = sorted(path.glob("*.tex"))
        if not tex_files:
            return []
        path = tex_files[0]
    if not path.is_file():
        return []
    try:
        tex = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return extract_question_stems(tex)


def item_has_tikzpicture(item_tex: str) -> bool:
    """True if the question block contains a TikZ picture environment."""
    return _TIKZ_RE.search(item_tex) is not None


def item_expects_figure(item_tex: str) -> bool:
    """True if marker ``% gambar soal ke N`` or a tikzpicture is present."""
    return item_has_gambar_marker(item_tex) or item_has_tikzpicture(item_tex)


def build_exam_question(number: int, item_tex: str) -> ExamQuestion | None:
    """Build one ``ExamQuestion`` from an enumerate item (stem required).

    ``number`` is the fallback index; ``% soal ke N`` overrides when present.
    Top-level ``steps`` are shared algebra only (pre-method). Alternate
    ``Metode N`` blocks go into ``methods`` and are not flattened into steps.
    """
    marked = extract_soal_number(item_tex)
    qnum = marked if marked is not None else number
    stem = extract_question_stem(item_tex)
    if stem is None:
        item_match = re.search(
            r"(\\item\s+(?:\$|\\displaystyle).*)",
            item_tex,
            re.DOTALL | re.IGNORECASE,
        )
        if item_match:
            stem = extract_question_stem(item_match.group(1))
        if stem is None:
            return None

    sections = _itemize_sections(item_tex)
    shared: list[str] = []
    methods: list[ExamMethod] = []
    milestones: list[ExamMilestone] = []
    has_sign = False
    has_critical = False
    saw_method = False

    if sections:
        for title, body in sections:
            method_match = _METHOD_TITLE_RE.match(title)
            if method_match is not None:
                saw_method = True
                label = method_match.group("label").strip()
                method_n = int(method_match.group("n"))
                method_steps = extract_align_steps(body)
                methods.append(
                    ExamMethod(
                        id=_method_id_from_label(label, method_n),
                        label=label,
                        steps=method_steps,
                        steps_symbolic=_symbolic_steps(method_steps),
                    )
                )
                continue

            if _SIGN_TITLE_RE.match(title):
                has_sign = True
                sign_steps = extract_align_steps(body)
                latex = " ; ".join(sign_steps) if sign_steps else title
                milestones.append(
                    ExamMilestone(
                        role="sign_chart",
                        latex=latex,
                        symbolic=latex_to_symbolic_payload(latex),
                        steps=sign_steps,
                        steps_symbolic=_symbolic_steps(sign_steps),
                    )
                )
                continue

            if _CRITICAL_TITLE_RE.match(title):
                has_critical = True
                crit_steps = extract_align_steps(body)
                latex = " ; ".join(crit_steps) if crit_steps else title
                milestones.append(
                    ExamMilestone(
                        role="critical_points",
                        latex=latex,
                        symbolic=latex_to_symbolic_payload(latex),
                        steps=crit_steps,
                        steps_symbolic=_symbolic_steps(crit_steps),
                    )
                )
                continue

            if _FIGURE_TITLE_RE.match(title) or _TIKZ_RE.search(body):
                continue

            if _HP_TITLE_RE.match(title):
                continue

            # Langkah-langkah / unlabeled algebra before methods → shared
            if not saw_method or _LANGKAH_TITLE_RE.match(title):
                shared.extend(extract_align_steps(body))
    else:
        # No itemize structure: keep legacy flat align extraction.
        shared = extract_align_steps(item_tex)

    # Single-path kunci (no Metode): top-level steps = all algebra aligns.
    if not methods and not sections:
        pass  # shared already full extract
    elif not methods and sections:
        # Itemize without Metode: all non-role aligns already collected as shared
        # from Langkah / default branch; if empty, fall back to full extract.
        if not shared:
            shared = extract_align_steps(item_tex)

    final = extract_hp_final(item_tex)

    expects_figure = item_expects_figure(item_tex)
    final_text = final or ""
    number_line = None
    if expects_figure and final_text:
        number_line = number_line_from_symbolic(
            latex_to_symbolic_payload(final_text)
        )
        if number_line is None:
            number_line = number_line_from_symbolic(final_text)
    if final_text:
        milestones.append(
            ExamMilestone(
                role="hp",
                latex=final_text,
                symbolic=latex_to_symbolic_payload(final_text),
            )
        )

    parts: list[ExamPart] = []
    order = 1
    if shared or methods:
        parts.append(ExamPart(kind="algebra", order=order))
        order += 1
    if has_critical:
        parts.append(ExamPart(kind="critical_points", order=order))
        order += 1
    if has_sign:
        parts.append(ExamPart(kind="sign_chart", order=order))
        order += 1
    if expects_figure:
        parts.append(ExamPart(kind="figure", order=order))
        order += 1
    if final_text:
        parts.append(ExamPart(kind="hp", order=order))

    return ExamQuestion(
        number=qnum,
        stem=stem,
        stem_symbolic=latex_to_symbolic_payload(stem),
        steps=shared,
        steps_symbolic=_symbolic_steps(shared),
        methods=methods,
        milestones=milestones,
        final=final_text,
        final_symbolic=(
            latex_to_symbolic_payload(final_text) if final_text else None
        ),
        expects_figure=expects_figure,
        number_line=number_line,
        parts=parts,
    )


def build_exam_schema(tex: str, *, source: str = "") -> ExamSchema:
    """Parse kunci TeX into a full ``ExamSchema`` (stems, steps, HP, figure flags)."""
    questions: list[ExamQuestion] = []
    for index, item in enumerate(split_enumerate_items(tex), start=1):
        question = build_exam_question(index, item)
        if question is not None:
            questions.append(question)
    return ExamSchema(source=source, questions=questions)


def format_recognition_stems_block(
    stems: list[tuple[int, str]] | None,
) -> str:
    """Render ``(number, stem)`` list for crop_math (stems only, no solutions)."""
    if not stems:
        return _NO_EXAM_KEY
    lines = [f"{number}. {stem}" for number, stem in stems if stem.strip()]
    return "\n".join(lines) if lines else _NO_EXAM_KEY


def format_recognition_question_block(schema: ExamSchema | None) -> str:
    """Render stem list for crop_math; include ``[expects_figure]`` flags only.

    Never includes steps or HP.
    """
    if schema is None or not schema.questions:
        return _NO_EXAM_KEY
    lines: list[str] = []
    for question in schema.questions:
        if not question.stem.strip():
            continue
        suffix = " [expects_figure]" if question.expects_figure else ""
        lines.append(f"{question.number}. {question.stem}{suffix}")
    return "\n".join(lines) if lines else _NO_EXAM_KEY


def load_exam_schema(standard_dir: Path | str) -> ExamSchema | None:
    """Load ``exam_schema.json`` from a standards dir; ``None`` if missing/invalid."""
    path = exam_schema_path(Path(standard_dir))
    if not path.is_file():
        return None
    try:
        return ExamSchema.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ingest_kunci_tex(tex: str, *, source_note: str = "") -> list[tuple[int, str]]:
    """Parse kunci TeX into ``(question_number, solution_tex)`` pairs (1-based).

    Honors ``% soal ke N`` for question numbers when present.
    """
    results: list[tuple[int, str]] = []
    for index, item in enumerate(split_enumerate_items(tex), start=1):
        question = build_exam_question(index, item)
        if question is None:
            continue
        if not (question.final or "").strip():
            continue
        rendered = render_standard_solution_tex(
            question=question,
            final=question.final,
            source_note=source_note or f"question {question.number}",
        )
        results.append((question.number, rendered))
    return results
