"""Render a PDF into per-page PNG images."""

from __future__ import annotations

from pathlib import Path

from app.functions.page_names import PAGES_METADATA_FILENAME
from app.interfaces.renderer import PdfRenderer
from app.models.page import RenderResult


class RenderController:
    def __init__(self, renderer: PdfRenderer) -> None:
        self._renderer = renderer

    def render(self, pdf_path: Path, output_dir: Path, dpi: int) -> RenderResult:
        output_dir = Path(output_dir)
        pages = self._renderer.render(Path(pdf_path), output_dir, dpi)
        return RenderResult(
            pages=pages,
            output_dir=output_dir,
            metadata_path=output_dir / PAGES_METADATA_FILENAME,
        )
