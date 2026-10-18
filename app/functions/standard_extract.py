"""Pure helpers to locate and extract standard-solution content."""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.functions.question_names import question_dir_name
from app.models.exam_schema import ExamQuestion, ExamSchema

_FINAL_ANSWER_MARKER = "% final answer"

_ALIGN_BLOCK_RE = re.compile(
    r"\\begin\{aligned\*?\}(?P<body>.*?)\\end\{aligned\*?\}"
    r"|"
    r"\\begin\{align\*?\}(?P<body2>.*?)\\end\{align\*?\}",
    re.DOTALL | re.IGNORECASE,
)


def standard_solution_path(
    standard_dir: Path,
    question_number: int,
    part_label: str = "",
) -> Path:
    """Return ``standards/.../solutions/question_NNN[a].tex`` path."""
    return (
        Path(standard_dir)
        / "solutions"
        / f"{question_dir_name(question_number, part_label)}.tex"
    )


def exam_schema_path(standard_dir: Path) -> Path:
    """Return ``standards/.../exam_schema.json`` path."""
    return Path(standard_dir) / "exam_schema.json"


def schema_question(
    schema: ExamSchema | None,
    question_number: int,
    part_label: str = "",
) -> ExamQuestion | None:
    """Return the ``ExamQuestion`` with ``number`` and ``part_label``, or None."""
    if schema is None:
        return None
    for question in schema.questions:
        if question.number == question_number and question.part_label == part_label:
            return question
    return None


def soal_stems(schema: ExamSchema | None) -> dict[int, str]:
    """Stem per soal number; a soal with sub-soal gets their shared lead-in."""
    grouped: dict[int, list[str]] = {}
    for question in schema.questions if schema is not None else []:
        grouped.setdefault(question.number, []).append(question.stem)
    stems: dict[int, str] = {}
    for number, group in grouped.items():
        if len(group) == 1:
            stems[number] = group[0]
            continue
        shared = os.path.commonprefix(group)
        cut = shared.rfind(" ")
        stems[number] = (shared[:cut] if cut > 0 else shared).strip() or group[0]
    return stems


def standard_final_text(
    schema_q: ExamQuestion | None,
    tex: str | None,
) -> str | None:
    """Prefer ``final_symbolic.repr``; then TeX ``% final answer``; then ``final``."""
    if schema_q is not None and schema_q.final_symbolic is not None:
        repr_text = (schema_q.final_symbolic.repr or "").strip()
        if repr_text:
            return repr_text
    if tex:
        from_tex = extract_final_answer_from_tex(tex)
        if from_tex:
            return from_tex
    if schema_q is not None:
        final = (schema_q.final or "").strip()
        if final:
            return final
    return None


def standard_step_texts(
    schema_q: ExamQuestion | None,
    tex: str | None,
) -> list[str]:
    """Prefer per-index ``steps_symbolic.repr``; fall back to TeX / ``steps``.

    With ``steps_symbolic`` the schema's shared rows set the length: the TeX
    file also holds every method / milestone block, which are not shared rows.
    """
    tex_steps = extract_solution_steps_from_tex(tex) if tex else []
    if schema_q is not None and schema_q.steps_symbolic:
        symbolic = schema_q.steps_symbolic
        length = len(symbolic)
        result: list[str] = []
        for index in range(length):
            repr_text = ""
            if index < len(symbolic) and symbolic[index] is not None:
                repr_text = (symbolic[index].repr or "").strip()  # type: ignore[union-attr]
            if repr_text:
                result.append(repr_text)
                continue
            if index < len(tex_steps) and tex_steps[index].strip():
                result.append(tex_steps[index].strip())
                continue
            if (
                schema_q.steps
                and index < len(schema_q.steps)
                and schema_q.steps[index].strip()
            ):
                result.append(schema_q.steps[index].strip())
                continue
            # Keep the slot so later standard steps keep their index.
            result.append("")
        return result

    if tex_steps:
        return tex_steps
    if schema_q is not None and schema_q.steps:
        return [(step or "").strip() for step in schema_q.steps]
    return []


def _method_step_texts(method) -> list[str]:
    result: list[str] = []
    symbolic = getattr(method, "steps_symbolic", None) or []
    latex_steps = getattr(method, "steps", None) or []
    length = max(len(symbolic), len(latex_steps))
    for index in range(length):
        repr_text = ""
        if index < len(symbolic) and symbolic[index] is not None:
            repr_text = (symbolic[index].repr or "").strip()
        if repr_text:
            result.append(repr_text)
            continue
        if index < len(latex_steps) and (latex_steps[index] or "").strip():
            result.append(latex_steps[index].strip())
            continue
        result.append("")
    return result


def standard_method_step_banks(
    schema_q: ExamQuestion | None,
    tex: str | None = None,
) -> list[tuple[str, list[str]]]:
    """Return ``(bank_id, step_texts)`` for best-method soft-align.

    Without methods: one ``shared`` bank from top-level steps (TeX fallback).
    With methods: one bank per method = shared steps + that method's steps.
    """
    shared = standard_step_texts(schema_q, tex)
    if schema_q is None or not schema_q.methods:
        if _bank_has_math(shared):
            return [("shared", shared)]
        return []

    banks: list[tuple[str, list[str]]] = []
    for method in schema_q.methods:
        method_steps = _method_step_texts(method)
        combined = list(shared) + method_steps
        if _bank_has_math(combined):
            banks.append((method.id or "method", combined))
    if not banks and _bank_has_math(shared):
        return [("shared", shared)]
    return banks


def _bank_has_math(steps: list[str]) -> bool:
    return any(step.strip() for step in steps)


def extract_final_answer_from_tex(text: str) -> str | None:
    """Return the first non-empty line after ``% final answer``, or None."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower().startswith(_FINAL_ANSWER_MARKER):
            for following in lines[index + 1 :]:
                candidate = following.strip()
                if not candidate:
                    continue
                if candidate.startswith("%"):
                    continue
                return candidate
            return None
    return None


def extract_solution_steps_from_tex(text: str) -> list[str]:
    """Extract ordered math rows from aligned/align environments.

    Content after ``% final answer`` is ignored. Rows are split on ``\\\\``
    and alignment ``&`` are stripped, but only outside nested environments and
    braces, so ``bmatrix`` / ``vmatrix`` / ``cases`` cells survive intact. A
    multi-column row (``a &= 1, & b &= 2``) yields one step per column pair.
    Continuation rows that begin with ``=`` keep only the RHS (``&= 2`` → ``2``).
    """
    marker_idx = text.lower().find(_FINAL_ANSWER_MARKER)
    source = text[:marker_idx] if marker_idx >= 0 else text

    steps: list[str] = []
    for match in _ALIGN_BLOCK_RE.finditer(source):
        block = match.group("body")
        if block is None:
            block = match.group("body2")
        if not block:
            continue
        for row in _split_align_rows(_COMMENT_RE.sub("", block)):
            for column in row:
                cleaned = _clean_align_row(column)
                if cleaned:
                    steps.append(cleaned)
    return steps


_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

_ROW_TOKEN_RE = re.compile(
    r"\\(?P<kind>begin|end)\s*\{[^{}]*\}"
    r"|(?P<newline>\\\\)"
    r"|(?P<escaped>\\[{}&%])"
    r"|(?P<amp>&)"
    r"|(?P<open>\{)"
    r"|(?P<close>\})"
)

_ROW_NOISE_RE = re.compile(r"\\(?:nonumber|notag)\b|\\(?:label|tag)\s*\{[^{}]*\}")


def _split_align_rows(block: str) -> list[list[str]]:
    """Rows of an align body; each row split into columns at even top-level ``&``."""
    rows: list[list[str]] = []
    columns: list[str] = []
    piece_start = 0
    pieces: list[str] = []
    amp_count = 0
    depth = 0
    for match in _ROW_TOKEN_RE.finditer(block):
        if match.group("kind") == "begin" or match.group("open") is not None:
            depth += 1
            continue
        if match.group("kind") == "end" or match.group("close") is not None:
            depth = max(0, depth - 1)
            continue
        if depth > 0 or match.group("escaped") is not None:
            continue
        pieces.append(block[piece_start : match.start()])
        piece_start = match.end()
        if match.group("amp") is not None:
            amp_count += 1
            if amp_count % 2 == 0:
                columns.append("".join(pieces))
                pieces = []
            continue
        columns.append("".join(pieces))
        rows.append(columns)
        columns, pieces, amp_count = [], [], 0
    pieces.append(block[piece_start:])
    columns.append("".join(pieces))
    rows.append(columns)
    return rows


def _clean_align_row(row: str) -> str:
    joined = _ROW_NOISE_RE.sub("", row)
    joined = " ".join(joined.split())
    joined = joined.rstrip(",;").strip()
    if joined.startswith("="):
        joined = joined.lstrip("=").strip()
    return joined
