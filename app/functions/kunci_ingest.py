"""Pure helpers to ingest kunci_jawaban TeX into standards solution files."""

from __future__ import annotations

import re
from pathlib import Path

from app.functions.standard_extract import (
    exam_schema_path,
    extract_solution_steps_from_tex,
)
from app.functions.symbolic_from_latex import latex_to_symbolic_payload
from app.models.exam_schema import ExamPart, ExamQuestion, ExamSchema

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

_SOAL_MARKER_RE = re.compile(
    r"%\s*soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_GAMBAR_MARKER_RE = re.compile(
    r"%\s*gambar\s+soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_JAWABAN_MARKER_RE = re.compile(
    r"%\s*jawaban\s+soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_SOAL_BLOCK_SPLIT_RE = re.compile(
    r"(?=%\s*soal\s+ke\s+\d+\b)",
    re.IGNORECASE,
)

_NO_EXAM_KEY = (
    "(no exam key provided; infer question_number from handwriting if visible)"
)


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


def extract_align_steps(item_tex: str) -> list[str]:
    """Extract align/aligned rows from one question block; strip ``\\quad\\text``."""
    raw_steps = extract_solution_steps_from_tex(item_tex)
    steps: list[str] = []
    for step in raw_steps:
        cleaned = _QUAD_TEXT_RE.sub("", step)
        cleaned = " ".join(cleaned.split())
        if cleaned:
            steps.append(cleaned)
    return steps


def extract_hp_final(item_tex: str) -> str | None:
    """Return HP math from ``HP: $...$``, or None."""
    match = _HP_RE.search(item_tex)
    if match is None:
        return None
    hp = match.group("hp").strip()
    hp = " ".join(hp.split())
    return hp or None


def render_standard_solution_tex(
    steps: list[str],
    final: str,
    *,
    source_note: str = "",
) -> str:
    """Build standards-format solution TeX (aligned + ``% final answer``)."""
    header = "% Ingested from kunci_jawaban"
    if source_note:
        header = f"{header} ({source_note})"
    lines = [header]
    if steps:
        lines.append(r"\begin{aligned}")
        for index, step in enumerate(steps):
            suffix = r" \\" if index < len(steps) - 1 else ""
            lines.append(f"{step}{suffix}")
        lines.append(r"\end{aligned}")
        lines.append("")
    lines.append("% final answer")
    lines.append(final.strip())
    lines.append("")
    return "\n".join(lines)


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
    """
    marked = extract_soal_number(item_tex)
    qnum = marked if marked is not None else number
    stem = extract_question_stem(item_tex)
    if stem is None:
        # Marker-first blocks: stem may follow comments before \\item
        item_for_stem = item_tex
        item_match = re.search(
            r"(\\item\s+(?:\$|\\displaystyle).*)",
            item_tex,
            re.DOTALL | re.IGNORECASE,
        )
        if item_match:
            stem = extract_question_stem(item_match.group(1))
        if stem is None:
            return None
    steps = extract_align_steps(item_tex)
    final = extract_hp_final(item_tex)
    if final is None and steps:
        final = steps[-1]
    expects_figure = item_expects_figure(item_tex)
    parts: list[ExamPart] = []
    order = 1
    if steps:
        parts.append(ExamPart(kind="algebra", order=order))
        order += 1
    if expects_figure:
        parts.append(ExamPart(kind="figure", order=order))
        order += 1
    if final:
        parts.append(ExamPart(kind="hp", order=order))
    final_text = final or ""
    return ExamQuestion(
        number=qnum,
        stem=stem,
        stem_symbolic=latex_to_symbolic_payload(stem),
        steps=steps,
        steps_symbolic=[latex_to_symbolic_payload(step) for step in steps],
        final=final_text,
        final_symbolic=(
            latex_to_symbolic_payload(final_text) if final_text else None
        ),
        expects_figure=expects_figure,
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
        marked = extract_soal_number(item)
        qnum = marked if marked is not None else index
        steps = extract_align_steps(item)
        final = extract_hp_final(item)
        if final is None and steps:
            final = steps[-1]
        if final is None:
            continue
        rendered = render_standard_solution_tex(
            steps,
            final,
            source_note=source_note or f"question {qnum}",
        )
        results.append((qnum, rendered))
    return results
