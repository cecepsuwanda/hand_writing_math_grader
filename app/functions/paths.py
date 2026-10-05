"""Path helpers for input/output layout."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path


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


def resolve_jawaban_pdf(pdf: Path, jawaban_dir: Path) -> Path:
    """Resolve a student answer PDF under ``jawaban_dir`` (see ``resolve_input_path``)."""
    return resolve_input_path(pdf, jawaban_dir)


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


def parse_path_choice(
    paths: Sequence[Path],
    raw: str,
    *,
    kind: str = "file",
    default_suffix: str | None = None,
    alias: Callable[[Path], str] | None = None,
) -> Path:
    """Map a menu choice (filename preferred, then 1-based index) to a path.

    ``alias`` supplies a display name (see ``shorten_pdf_name``) that is also
    accepted, so a name the menu shows shortened can still be typed.

    Raises:
        ValueError: if the selection is empty or does not match.
    """
    choice = raw.strip()
    if not choice:
        raise ValueError("empty selection")
    if not paths:
        raise ValueError(f"no {kind}s available")

    lowered = choice.lower()
    for path in paths:
        name = path.name.lower()
        if name == lowered:
            return path
        if default_suffix and name == f"{lowered}{default_suffix.lower()}":
            return path

    if alias is not None:
        for path in paths:
            short = alias(path).lower()
            if short == lowered:
                return path
            if default_suffix and short == f"{lowered}{default_suffix.lower()}":
                return path

    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(paths):
            return paths[index - 1]
        raise ValueError(f"choice out of range: {choice}")

    raise ValueError(f"unknown {kind}: {choice}")


def parse_pdf_choice(pdfs: Sequence[Path], raw: str) -> Path:
    """Map a menu choice (filename preferred, then 1-based index) to a PDF path."""
    return parse_path_choice(
        pdfs, raw, kind="PDF", default_suffix=".pdf", alias=shorten_pdf_name
    )


def parse_kunci_choice(tex_files: Sequence[Path], raw: str) -> Path:
    """Map a menu choice to a kunci ``.tex`` path."""
    return parse_path_choice(tex_files, raw, kind="kunci", default_suffix=".tex")


def parse_run_choice(run_dirs: Sequence[Path], raw: str) -> Path:
    """Map a menu choice (folder name or 1-based index) to a run directory."""
    return parse_path_choice(run_dirs, raw, kind="run")
