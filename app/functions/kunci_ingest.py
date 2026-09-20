"""Pure helpers to ingest kunci_jawaban TeX into standards solution files."""

from __future__ import annotations

import re

from app.functions.standard_extract import extract_solution_steps_from_tex

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

_HP_RE = re.compile(
    r"HP:\s*\$(?P<hp>.+?)\$",
    re.IGNORECASE | re.DOTALL,
)

_QUAD_TEXT_RE = re.compile(
    r"\\quad\s*\\text\{[^{}]*\}",
)


def split_enumerate_items(tex: str) -> list[str]:
    """Return outer enumerate question blocks (math-led ``\\item`` only)."""
    match = _ENUMERATE_BODY_RE.search(tex)
    if match is None:
        return []
    body = match.group("body")
    chunks = _QUESTION_ITEM_SPLIT_RE.split(body)
    items: list[str] = []
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


def ingest_kunci_tex(tex: str, *, source_note: str = "") -> list[tuple[int, str]]:
    """Parse kunci TeX into ``(question_number, solution_tex)`` pairs (1-based)."""
    results: list[tuple[int, str]] = []
    for index, item in enumerate(split_enumerate_items(tex), start=1):
        steps = extract_align_steps(item)
        final = extract_hp_final(item)
        if final is None and steps:
            final = steps[-1]
        if final is None:
            continue
        rendered = render_standard_solution_tex(
            steps,
            final,
            source_note=source_note or f"question {index}",
        )
        results.append((index, rendered))
    return results
