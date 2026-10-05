"""Pure view-model builder for the per-student LaTeX report (report.tex)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.functions.latex_transforms import escape_latex_text, strip_final_answer_prefix
from app.functions.report_aggregate import format_score
from app.models.grading import StepGrade
from app.models.question import StudentStep
from app.models.latex_report import (
    LatexFigureRow,
    LatexQuestionView,
    LatexReportView,
    LatexStepRow,
    LatexSummaryRow,
)
from app.models.report import MISSING_UNANSWERED, ExamReport, QuestionReportDetail
from app.models.validation import ValidationStatus

EMPTY_CELL = "---"
PART_FEEDBACK_PREFIX = "part:"

# pdflatex + inputenc cannot typeset these directly in math mode.
_UNICODE_MATH = {
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "−": "-",
    "×": r"\times",
    "÷": r"\div",
    "∞": r"\infty",
    "·": r"\cdot",
    "∈": r"\in",
    "∪": r"\cup",
    "∩": r"\cap",
    "→": r"\to",
    "√": r"\surd",
    "±": r"\pm",
}

_UNICODE_TEXT = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "--",
    "\u2014": "---",
    "\u2018": "`",
    "\u2019": "'",
    "\u201c": "``",
    "\u201d": "''",
    "\u2026": "...",
    "\u00a0": " ",
}

_MATH_WRAPPERS = (("$$", "$$"), ("$", "$"), (r"\(", r"\)"), (r"\[", r"\]"))
# ``\left``/``\right`` delimiters only — not ``\leftarrow`` / ``\rightarrow``.
_LEFT_DELIM = re.compile(r"\\left(?![A-Za-z])")
_RIGHT_DELIM = re.compile(r"\\right(?![A-Za-z])")
# Display/inline switches are illegal inside the report's own ``$...$``.
_MATH_MODE_SWITCH = re.compile(r"\\[\[\]()]")
# ``x_`` / ``x^{}``-less script at the end or right before a closing brace.
_DANGLING_SCRIPT = re.compile(r"[_^]\s*(?:$|\})")
# OCR sometimes emits escape sequences (``\n`` line breaks) as two literal characters.
_LITERAL_ESCAPE = re.compile(r"(?<!\\)\\[nrt](?![A-Za-z])")
_LITERAL_ESCAPE_SEPARATOR = r" \quad "
_CONTROL_WORD = re.compile(r"\\([A-Za-z]+)")
_GREEK_LETTERS = frozenset(
    """
    alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
    lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi
    psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
    """.split()
)
# Anything outside this set falls back to ``\texttt`` instead of reaching pdflatex.
_MATH_COMMANDS = (
    frozenset(macro.lstrip("\\") for macro in _UNICODE_MATH.values() if macro.startswith("\\"))
    | frozenset(
        """
        frac dfrac tfrac sqrt surd le leq ge geq lt gt ne neq infty cup cap cdot
        times div pm mp in notin to implies iff Rightarrow rightarrow Leftarrow
        leftarrow Leftrightarrow leftrightarrow Longrightarrow quad qquad left
        right text mathrm mathbb mathbf emptyset varnothing ldots cdots dots circ
        mid setminus subset subseteq approx equiv vert lvert rvert lbrace rbrace
        langle rangle land lor neg wedge vee forall exists therefore because
        displaystyle
        """.split()
    )
    | _GREEK_LETTERS
)
_UNSAFE_PATH_CHARS = frozenset("#%&~$^{}\\")

_STATUS_COLORS = {
    ValidationStatus.VALID.value: "green!50!black",
    ValidationStatus.INVALID.value: "red!70!black",
    ValidationStatus.UNCERTAIN.value: "orange!80!black",
}


def _replace_unicode_math(text: str, *, wrap: bool) -> str:
    parts: list[str] = []
    for char in text:
        macro = _UNICODE_MATH.get(char)
        if macro is None:
            parts.append(char)
        elif wrap:
            parts.append(f"${macro}$")
        else:
            parts.append(f" {macro} ")
    return "".join(parts)


def _scan_unsafe(text: str, forbidden: str) -> bool:
    """True when braces are unbalanced or an unescaped forbidden char appears."""
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            nxt = text[index + 1] if index + 1 < len(text) else ""
            if nxt in ("\\", ""):
                return True
            index += 2
            continue
        if char in forbidden:
            return True
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return True
        index += 1
    return depth != 0


def _has_environment(text: str) -> bool:
    return "\\begin" in text or "\\end" in text


def latex_text(text: str) -> str:
    """Escape prose for LaTeX text mode; unsupported glyphs become ``?``."""
    plain = "".join(_UNICODE_TEXT.get(c, c) for c in text)
    escaped = _replace_unicode_math(escape_latex_text(" ".join(plain.split())), wrap=True)
    return "".join(c if ord(c) <= 0xFF else "?" for c in escaped)


def _breakable(escaped: str) -> str:
    """Let long ``snake_case`` tokens wrap inside narrow table cells."""
    return escaped.replace(r"\_", r"\_\allowbreak{}")


def latex_code(text: str) -> str:
    """Verbatim-looking fallback for strings that are not safe as LaTeX."""
    cleaned = latex_text(text)
    return rf"\texttt{{{cleaned}}}" if cleaned else ""


def _strip_math_wrapper(text: str) -> str:
    """``$x$`` / ``$$x$$`` / ``\\(x\\)`` / ``\\[x\\]`` → ``x`` (report adds its own)."""
    for opener, closer in _MATH_WRAPPERS:
        if (
            len(text) > len(opener) + len(closer)
            and text.startswith(opener)
            and text.endswith(closer)
        ):
            return text[len(opener) : -len(closer)].strip()
    return text


def _delimiters_unbalanced(text: str) -> bool:
    return len(_LEFT_DELIM.findall(text)) != len(_RIGHT_DELIM.findall(text))


def _has_unknown_command(text: str) -> bool:
    return any(word not in _MATH_COMMANDS for word in _CONTROL_WORD.findall(text))


def normalize_literal_escapes(text: str) -> str:
    """Literal ``\\n`` / ``\\r`` / ``\\t`` → ``\\quad`` (keeps ``\\ne``, ``\\to``, ``\\right``)."""
    return _LITERAL_ESCAPE.sub(lambda _: _LITERAL_ESCAPE_SEPARATOR, text)


def latex_math_or_text(raw: str) -> str:
    """Render an OCR LaTeX fragment as inline math, or as escaped code if unsafe."""
    collapsed = " ".join(normalize_literal_escapes(raw or "").split())
    if not collapsed:
        return ""
    inner = _strip_math_wrapper(collapsed)
    candidate = " ".join(_replace_unicode_math(inner, wrap=False).split())
    unsafe = (
        not candidate
        or not candidate.isascii()
        or _scan_unsafe(candidate, "&%#$")
        or _has_environment(candidate)
        or _delimiters_unbalanced(candidate)
        or _MATH_MODE_SWITCH.search(candidate) is not None
        or _DANGLING_SCRIPT.search(candidate) is not None
        or _has_unknown_command(candidate)
    )
    if unsafe:
        return latex_code(collapsed)
    return rf"$\displaystyle {candidate}$"


def _script_outside_math(text: str) -> bool:
    """True when ``_``/``^`` appear in text mode (outside unescaped ``$...$``)."""
    in_math = False
    for index, char in enumerate(text):
        escaped = index > 0 and text[index - 1] == "\\"
        if char == "$" and not escaped:
            in_math = not in_math
        elif char in "_^" and not escaped and not in_math:
            return True
    return False


def latex_stem(stem: str) -> str:
    """Question text from ``question_crops`` (prose with ``$...$`` math)."""
    collapsed = " ".join(normalize_literal_escapes(stem or "").split())
    if not collapsed:
        return ""
    dollar_count = sum(
        1
        for i, c in enumerate(collapsed)
        if c == "$" and (i == 0 or collapsed[i - 1] != "\\")
    )
    unsafe = (
        any(ord(c) > 0xFF for c in collapsed)
        or dollar_count % 2 != 0
        or _scan_unsafe(collapsed, "&%#")
        or _has_environment(collapsed)
        or _script_outside_math(collapsed)
    )
    return latex_code(collapsed) if unsafe else collapsed


def graphics_path(path: Path, base_dir: Path) -> str:
    """Path for ``\\includegraphics`` relative to the report folder (POSIX)."""
    path = Path(path)
    try:
        return Path(os.path.relpath(path, Path(base_dir))).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def is_graphics_path_safe(path: str) -> bool:
    """``\\includegraphics`` cannot take these characters from a raw path."""
    return not any(c in _UNSAFE_PATH_CHARS for c in path)


def _score_cell(grade: StepGrade | None) -> str:
    if grade is None:
        return EMPTY_CELL
    return f"{format_score(grade.score)}/{format_score(grade.max_score)}"


def _status_cell(grade: StepGrade | None) -> tuple[str, str]:
    if grade is None:
        return EMPTY_CELL, "black"
    value = grade.validation_status.value
    return value, _STATUS_COLORS.get(value, "black")


def _step_ocr(step: StudentStep) -> str:
    rendered = latex_math_or_text(step.raw_text)
    if rendered:
        return rendered
    if step.symbolic is not None and (step.symbolic.repr or "").strip():
        return latex_code(step.symbolic.repr)
    return EMPTY_CELL


def _step_row(number: str, ocr: str, role: str, grade: StepGrade | None) -> LatexStepRow:
    status, color = _status_cell(grade)
    comment = latex_text(grade.feedback) if grade is not None else ""
    return LatexStepRow(
        number=number,
        ocr=ocr or EMPTY_CELL,
        role=_breakable(latex_text(role)) or EMPTY_CELL,
        status=status,
        status_color=color,
        score=_score_cell(grade),
        comment=comment or EMPTY_CELL,
    )


def _split_part_feedback(feedback: str) -> tuple[str, str]:
    """``part:figure; reason`` → (``figure``, ``reason``)."""
    if not feedback.startswith(PART_FEEDBACK_PREFIX):
        return "", feedback
    head, _, rest = feedback[len(PART_FEEDBACK_PREFIX) :].partition(";")
    return head.strip(), rest.strip()


def _part_row(grade: StepGrade, fallback_id: str) -> LatexStepRow:
    part_id, reason = _split_part_feedback(grade.feedback)
    part_id = part_id or fallback_id
    status, color = _status_cell(grade)
    return LatexStepRow(
        number=_breakable(latex_text(part_id)) or EMPTY_CELL,
        ocr=EMPTY_CELL,
        status=status,
        status_color=color,
        score=_score_cell(grade),
        comment=latex_text(reason) or EMPTY_CELL,
    )


def build_question_view(detail: QuestionReportDetail, base_dir: Path) -> LatexQuestionView:
    question = detail.question
    grade = detail.grade
    step_grades = {
        g.step_number: g for g in (grade.steps if grade else []) if g.step_number > 0
    }

    steps = [
        _step_row(
            str(step.step_number),
            _step_ocr(step),
            step.role or "",
            step_grades.get(step.step_number),
        )
        for step in question.student_steps
    ]
    known = {step.step_number for step in question.student_steps}
    steps.extend(
        _step_row(str(number), EMPTY_CELL, "", step_grades[number])
        for number in sorted(step_grades)
        if number not in known
    )

    # Part grades carry an explicit ``part_id``; older grading.json files predate
    # it and only ordered ``part_statuses``, so fall back to position there.
    part_grades = [g for g in (grade.steps if grade else []) if g.step_number == 0]
    fallback_ids = list((grade.part_statuses or {}).keys()) if grade else []
    parts = [
        _part_row(
            g,
            g.part_id
            or (fallback_ids[i] if i < len(fallback_ids) else ""),
        )
        for i, g in enumerate(part_grades)
    ]

    final_text = strip_final_answer_prefix(question.student_final_answer or "")
    final_ocr = latex_math_or_text(final_text)
    if not final_ocr and question.student_final_symbolic is not None:
        final_ocr = latex_code(question.student_final_symbolic.repr or "")
    final = None
    if final_ocr or (grade is not None and grade.final_answer is not None):
        final = _step_row(
            "akhir", final_ocr, "", grade.final_answer if grade else None
        )

    figures = [
        LatexFigureRow(
            caption=latex_text(fig.caption or ""),
            symbolic=latex_code(fig.symbolic.repr) if fig.symbolic and fig.symbolic.repr else "",
        )
        for fig in question.figure_refs
        if (fig.caption or "").strip() or (fig.symbolic and fig.symbolic.repr)
    ]

    images: list[str] = []
    missing = list(detail.missing_crops)
    for crop in detail.crop_images:
        rel = graphics_path(crop, base_dir)
        if is_graphics_path_safe(rel):
            images.append(rel)
        else:
            missing.append(f"{Path(crop).name} (path tidak aman untuk LaTeX: {rel})")

    return LatexQuestionView(
        title=f"Soal {question.question_number}",
        stem=latex_stem(detail.stem),
        images=images,
        missing_images=[latex_text(name) for name in missing],
        steps=steps,
        parts=parts,
        final=final,
        figures=figures,
        score=format_score(grade.score) if grade else "",
        maximum=format_score(grade.maximum_score) if grade else "",
        review_status=latex_text(grade.review_status.value) if grade else "",
        graded=grade is not None,
    )


def build_latex_report_context(
    exam: ExamReport,
    details: list[QuestionReportDetail],
    base_dir: Path,
) -> LatexReportView:
    meta = exam.metadata
    versions = meta.prompt_versions
    ordered = sorted(details, key=lambda d: d.question.question_number)
    return LatexReportView(
        student_id=_breakable(latex_text(meta.student_id)),
        total=format_score(exam.total_score),
        maximum=format_score(exam.maximum_total),
        overall_status=latex_text(exam.overall_status.value),
        summary=[
            LatexSummaryRow(
                number=row.question_number,
                score=format_score(row.score),
                maximum=format_score(row.maximum_score),
                status=latex_text(
                    f"{row.missing_label or MISSING_UNANSWERED}, {row.review_status.value}"
                    if row.missing
                    else row.review_status.value
                ),
            )
            for row in exam.questions
        ],
        questions=[build_question_view(d, base_dir) for d in ordered],
        generated_at=latex_text(meta.generated_at),
        vision_model=latex_text(meta.vision_model) or EMPTY_CELL,
        reasoning_model=latex_text(meta.reasoning_model) or EMPTY_CELL,
        prompt_versions=latex_text(
            f"recognition={versions.recognition}, "
            f"validation={versions.validation}, "
            f"grading={versions.grading}"
        ),
    )
