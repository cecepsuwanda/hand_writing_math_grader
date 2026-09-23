"""Path helpers for input/output layout."""

from __future__ import annotations

from pathlib import Path
from typing import Literal


MainMenuChoice = Literal["ingest", "process", "exit"]


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


def resolve_jawaban_pdf(pdf: Path, jawaban_dir: Path) -> Path:
    """Resolve a student answer PDF, preferring ``jawaban_dir`` when needed.

    Search order:
    1. ``pdf`` as given (cwd-relative or absolute)
    2. ``jawaban_dir / pdf`` (relative path under jawaban)
    3. ``jawaban_dir / pdf.name`` (bare filename under jawaban)
    """
    pdf = Path(pdf)
    jawaban_dir = Path(jawaban_dir)
    candidates = [pdf]
    if not pdf.is_absolute():
        under_dir = jawaban_dir / pdf
        if under_dir not in candidates:
            candidates.append(under_dir)
        by_name = jawaban_dir / pdf.name
        if by_name not in candidates:
            candidates.append(by_name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return pdf


def parse_path_choice(
    paths: list[Path],
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


def parse_pdf_choice(pdfs: list[Path], raw: str) -> Path:
    """Map a menu choice (filename preferred, then 1-based index) to a PDF path."""
    return parse_path_choice(pdfs, raw, kind="PDF", default_suffix=".pdf")


def parse_kunci_choice(tex_files: list[Path], raw: str) -> Path:
    """Map a menu choice to a kunci ``.tex`` path."""
    return parse_path_choice(tex_files, raw, kind="kunci", default_suffix=".tex")


def parse_main_menu_choice(raw: str) -> MainMenuChoice:
    """Parse main menu input into ``ingest`` / ``process`` / ``exit``.

    Raises:
        ValueError: if the choice is empty or unknown.
    """
    choice = raw.strip().lower()
    if not choice:
        raise ValueError("empty selection")
    if choice in {"1", "ingest", "kunci", "i"}:
        return "ingest"
    if choice in {"2", "process", "pdf", "proses", "p"}:
        return "process"
    if choice in {"3", "exit", "keluar", "q"}:
        return "exit"
    raise ValueError(f"unknown menu choice: {raw.strip()}")
