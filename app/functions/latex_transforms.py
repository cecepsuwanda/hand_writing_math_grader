"""Pure LaTeX formatting helpers for student solutions."""

from __future__ import annotations

import re
from pathlib import Path

from app.functions.question_names import latex_source_filename
from app.models.question import Question, StudentStep

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Longer operators first so \neq / \le match before single-char tokens.
_ALIGN_OPS = (
    r"\\neq",
    r"\\ne",
    r"\\leq",
    r"\\le",
    r"\\geq",
    r"\\ge",
    r"\\leqslant",
    r"\\geqslant",
    r"\\approx",
    r"\\equiv",
    "=",
    r"\\lt",
    r"\\gt",
    "<",
    ">",
    "≠",
    "≤",
    "≥",
)

_ALIGN_OP_RE = re.compile(
    "|".join(sorted((_ALIGN_OPS), key=len, reverse=True))
)

_FINAL_ANSWER_PREFIX_RE = re.compile(
    r"^(?:jawaban\s+akhir|final\s+answer)\s*[:：-]?\s*",
    re.IGNORECASE,
)


def escape_latex_text(text: str) -> str:
    """Escape characters that are special in LaTeX text mode."""
    parts: list[str] = []
    for char in text:
        parts.append(_LATEX_SPECIALS.get(char, char))
    return "".join(parts)


def normalize_step_latex(step: StudentStep) -> str:
    """Prefer symbolic.repr for display; else deprecated latex; else escaped raw_text."""
    if step.symbolic is not None and (step.symbolic.repr or "").strip():
        return " ".join(step.symbolic.repr.split())
    latex = (step.latex or "").strip()
    if latex:
        return " ".join(latex.split())
    raw = (step.raw_text or "").strip()
    if not raw:
        return ""
    collapsed = " ".join(raw.split())
    return escape_latex_text(collapsed)


def format_aligned_line(expression: str) -> str:
    """Insert & before the first relation operator when present."""
    expr = expression.strip()
    if not expr:
        return ""
    match = _ALIGN_OP_RE.search(expr)
    if not match or match.start() == 0:
        return expr
    left = expr[: match.start()].rstrip()
    op = match.group(0)
    right = expr[match.end() :].lstrip()
    if not left:
        return expr
    return f"{left} &{op} {right}".rstrip()


def strip_final_answer_prefix(text: str) -> str:
    """Remove prose prefixes from final-answer display only."""
    cleaned = text.strip()
    if not cleaned:
        return ""
    stripped = _FINAL_ANSWER_PREFIX_RE.sub("", cleaned).strip()
    return stripped if stripped else cleaned


def build_student_latex(
    question: Question,
    *,
    question_dir: Path | None = None,
) -> str:
    """Build derived student.tex; prefer recognition latex_source sidecar when present."""
    header = [
        f"% {question.question_id}",
        "% Derived audit file; question.json holds symbolic/raw_text only (no LaTeX).",
    ]

    if question_dir is not None:
        sidecar = Path(question_dir) / latex_source_filename()
        if sidecar.is_file():
            body = sidecar.read_text(encoding="utf-8").strip()
            if body:
                return "\n".join(header) + "\n\n" + body + "\n"

    lines: list[str] = list(header)

    step_exprs = [
        normalize_step_latex(step)
        for step in question.student_steps
        if normalize_step_latex(step)
    ]

    if step_exprs:
        lines.append(r"\begin{aligned}")
        for index, expr in enumerate(step_exprs):
            aligned = format_aligned_line(expr)
            suffix = r" \\" if index < len(step_exprs) - 1 else ""
            lines.append(f"{aligned}{suffix}")
        lines.append(r"\end{aligned}")
    else:
        lines.append("% (no steps)")

    for fig in question.figure_refs:
        caption = escape_latex_text(fig.caption or "")
        lines.append(f"% figure: {caption}")
        lines.append(rf"\includegraphics{{{fig.path}}}")

    final = ""
    if question.student_final_symbolic is not None:
        final = (question.student_final_symbolic.repr or "").strip()
    if not final:
        final = strip_final_answer_prefix(question.student_final_answer or "")
    lines.append("")
    lines.append("% final answer")
    if final:
        if _ALIGN_OP_RE.search(final) or re.search(r"[0-9a-zA-Z]", final):
            if "\\" in final or _ALIGN_OP_RE.search(final):
                lines.append(final)
            else:
                if re.fullmatch(r"[0-9a-zA-Z\s+\-*/().<>=≤≥≠]+", final):
                    lines.append(final)
                else:
                    lines.append(escape_latex_text(final))
        else:
            lines.append(escape_latex_text(final))
    else:
        lines.append("% (empty)")

    return "\n".join(lines) + "\n"
