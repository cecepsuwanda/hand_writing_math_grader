"""Path helpers for input/output layout."""

from __future__ import annotations

from pathlib import Path

from app.models.defaults import DEFAULT_STUDENT_ID


def list_jawaban_pdfs(jawaban_dir: Path) -> list[Path]:
    """Return sorted ``*.pdf`` files directly under ``jawaban_dir``."""
    jawaban_dir = Path(jawaban_dir)
    if not jawaban_dir.is_dir():
        return []
    return sorted(
        (p for p in jawaban_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.name.lower(),
    )


def list_kunci_tex(kunci_dir: Path) -> list[Path]:
    """Return sorted ``*.tex`` files directly under ``kunci_dir``."""
    kunci_dir = Path(kunci_dir)
    if not kunci_dir.is_dir():
        return []
    return sorted(
        (p for p in kunci_dir.iterdir() if p.is_file() and p.suffix.lower() == ".tex"),
        key=lambda p: p.name.lower(),
    )


def resolve_input_path(path: Path, base_dir: Path) -> Path:
    """Resolve an input file, preferring ``base_dir`` when needed.

    Search order:
    1. ``path`` as given (cwd-relative or absolute)
    2. ``base_dir / path`` (relative path under base_dir)
    3. ``base_dir / path.name`` (bare filename under base_dir)

    Returns ``path`` unchanged when no candidate exists.
    """
    path = Path(path)
    base_dir = Path(base_dir)
    candidates = [path]
    if not path.is_absolute():
        under_dir = base_dir / path
        if under_dir not in candidates:
            candidates.append(under_dir)
        by_name = base_dir / path.name
        if by_name not in candidates:
            candidates.append(by_name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return path


def shorten_pdf_name(pdf: Path) -> str:
    """Shortened, lower-case display name for an LMS-style PDF.

    Moodle exports read::

        <full name>_<id>_assignsubmission_file_<topic>_<name>_<student id>.pdf

    The short name keeps the name (minus its first word), the student id, and
    the topic, joined by underscores. Anything else falls back to the plain
    lower-cased file name with spaces turned into underscores.
    """
    pdf = Path(pdf)
    parts = pdf.stem.split("_")
    marker = next(
        (
            index
            for index in range(len(parts) - 1)
            if parts[index].lower() == "assignsubmission"
            and parts[index + 1].lower() == "file"
        ),
        None,
    )
    if marker is None:
        return pdf.name.lower().replace(" ", "_")

    topic_part = parts[marker + 2] if marker + 2 < len(parts) else ""
    name_part = parts[marker + 3] if marker + 3 < len(parts) else ""
    student_id = parts[marker + 4] if marker + 4 < len(parts) else ""

    topic_clean = "_".join(topic_part.lower().split())
    name_words = name_part.split()
    if len(name_words) > 1:
        # The first word is the repeated given name in Moodle exports.
        name_words = name_words[1:]
    name_clean = "_".join(word.lower() for word in name_words)
    components = [c for c in [name_clean, student_id.lower(), topic_clean] if c]
    return "_".join(components) + pdf.suffix.lower()


_NIM_MIN_DIGITS = 8


def student_id_from_pdf_stem(stem: str, fallback: str = DEFAULT_STUDENT_ID) -> str:
    """Student id for a PDF / run folder name: the NIM, else the Moodle name.

    The NIM is the last all-digit ``_`` part of at least eight digits (the
    Moodle submission id is shorter). Without one, a Moodle export still names
    the student in its first part; anything else gets ``fallback``.
    """
    parts = [part.strip() for part in stem.split("_")]
    nims = [p for p in parts if p.isdigit() and len(p) >= _NIM_MIN_DIGITS]
    if nims:
        return nims[-1]
    lowered = [p.lower() for p in parts]
    if "assignsubmission" in lowered and parts[0]:
        return "_".join(parts[0].lower().split())
    return fallback
