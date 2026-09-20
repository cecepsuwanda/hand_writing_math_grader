"""Path helpers for input/output layout."""

from __future__ import annotations

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


def parse_pdf_choice(pdfs: list[Path], raw: str) -> Path:
    """Map a menu choice (1-based index or filename) to a PDF path.

    Raises:
        ValueError: if the selection is empty or does not match.
    """
    choice = raw.strip()
    if not choice:
        raise ValueError("empty selection")
    if not pdfs:
        raise ValueError("no PDFs available")

    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(pdfs):
            return pdfs[index - 1]
        raise ValueError(f"choice out of range: {choice}")

    lowered = choice.lower()
    for pdf in pdfs:
        if pdf.name.lower() == lowered or pdf.name.lower() == f"{lowered}.pdf":
            return pdf
    raise ValueError(f"unknown PDF: {choice}")
