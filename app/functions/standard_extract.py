"""Pure helpers to locate and extract standard-solution content."""

from __future__ import annotations

import re
from pathlib import Path

from app.functions.question_names import question_dir_name

_FINAL_ANSWER_MARKER = "% final answer"

_ALIGN_BLOCK_RE = re.compile(
    r"\\begin\{aligned\*?\}(?P<body>.*?)\\end\{aligned\*?\}"
    r"|"
    r"\\begin\{align\*?\}(?P<body2>.*?)\\end\{align\*?\}",
    re.DOTALL | re.IGNORECASE,
)


def standard_solution_path(standard_dir: Path, question_number: int) -> Path:
    """Return ``standards/.../solutions/question_NNN.tex`` path."""
    return (
        Path(standard_dir)
        / "solutions"
        / f"{question_dir_name(question_number)}.tex"
    )


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

    Content after ``% final answer`` is ignored. Rows are split on ``\\\\``;
    ``&`` alignment tabs are stripped. Continuation rows that begin with ``=``
    keep only the RHS (e.g. ``&= 2`` → ``2``).
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
        for row in re.split(r"\\\\", block):
            cleaned = _clean_align_row(row)
            if cleaned:
                steps.append(cleaned)
    return steps


def _clean_align_row(row: str) -> str:
    pieces: list[str] = []
    for line in row.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        if "%" in stripped:
            stripped = re.split(r"(?<!\\)%", stripped, maxsplit=1)[0].strip()
        if stripped:
            pieces.append(stripped)
    if not pieces:
        return ""
    joined = " ".join(pieces)
    joined = joined.replace("&", "")
    joined = " ".join(joined.split())
    if joined.startswith("="):
        joined = joined.lstrip("=").strip()
    return joined
