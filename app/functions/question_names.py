"""Deterministic question artifact names."""

import re

_PART_LABEL_RE = re.compile(r"[a-z]{0,4}")
_QUESTION_REF_RE = re.compile(r"(?P<number>\d+)(?P<part>[a-z]{0,4})")


def question_dir_name(question_number: int, part_label: str = "") -> str:
    """``(1, "")`` → ``question_001``; ``(1, "a")`` → ``question_001a``."""
    if question_number < 1:
        raise ValueError(f"question_number must be >= 1, got {question_number}")
    if not _PART_LABEL_RE.fullmatch(part_label):
        raise ValueError(f"part_label must be 0-4 lowercase letters, got {part_label!r}")
    return f"question_{question_number:03d}{part_label}"


def split_question_ref(ref: str) -> tuple[int, str]:
    """``question_007b`` / ``7b`` / ``7`` → ``(7, "b")`` / ``(7, "")``.

    Raises:
        ValueError: if ``ref`` carries no positive question number.
    """
    raw = ref.strip().removeprefix("question_").lower()
    match = _QUESTION_REF_RE.fullmatch(raw)
    if match is None or int(match.group("number")) < 1:
        raise ValueError(f"not a question reference: {ref!r}")
    return int(match.group("number")), match.group("part")


def parse_question_ref(ref: str) -> str:
    """``question_007`` / ``question_7`` / ``7`` / ``7a`` → canonical ``question_007[a]``.

    Raises:
        ValueError: if ``ref`` carries no positive question number.
    """
    return question_dir_name(*split_question_ref(ref))


def question_artifact_filename() -> str:
    return "question.json"


def student_tex_filename() -> str:
    return "student.tex"


def latex_source_filename() -> str:
    """Sidecar from recognition latex_document (not stored in question.json)."""
    return "latex_source.tex"


def validation_filename() -> str:
    return "validation.json"


def grading_filename() -> str:
    return "grading.json"


def report_json_filename() -> str:
    return "report.json"


def summary_csv_filename() -> str:
    return "summary.csv"


def report_html_filename() -> str:
    return "report.html"


def report_tex_filename() -> str:
    return "report.tex"
