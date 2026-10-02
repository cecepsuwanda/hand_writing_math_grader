"""Path helpers for input/output layout."""

from __future__ import annotations

from collections.abc import Sequence
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


def parse_path_choice(
    paths: Sequence[Path],
    raw: str,
    *,
    kind: str = "file",
    default_suffix: str | None = None,
) -> Path:
    """Map a menu choice (filename preferred, then 1-based index) to a path.

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

    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(paths):
            return paths[index - 1]
        raise ValueError(f"choice out of range: {choice}")

    raise ValueError(f"unknown {kind}: {choice}")


def parse_pdf_choice(pdfs: Sequence[Path], raw: str) -> Path:
    """Map a menu choice (filename preferred, then 1-based index) to a PDF path."""
    return parse_path_choice(pdfs, raw, kind="PDF", default_suffix=".pdf")


def parse_kunci_choice(tex_files: Sequence[Path], raw: str) -> Path:
    """Map a menu choice to a kunci ``.tex`` path."""
    return parse_path_choice(tex_files, raw, kind="kunci", default_suffix=".tex")


def parse_run_choice(run_dirs: Sequence[Path], raw: str) -> Path:
    """Map a menu choice (folder name or 1-based index) to a run directory."""
    return parse_path_choice(run_dirs, raw, kind="run")
