"""PyMuPDF adapter that renders PDF pages to PNG artifacts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pymupdf

from app.exceptions import (
    EmptyPdfError,
    InvalidPdfError,
    InvalidRenderSettingsError,
    PageRenderError,
    PdfNotFoundError,
)
from app.functions.page_names import PAGES_METADATA_FILENAME, page_image_filename
from app.interfaces.renderer import PdfRenderer
from app.models.page import Page

logger = logging.getLogger(__name__)


class PyMuPdfRenderer(PdfRenderer):
    def render(self, pdf_path: Path, output_dir: Path, dpi: int) -> list[Page]:
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        if dpi <= 0:
            raise InvalidRenderSettingsError("dpi must be a positive integer")
        if not pdf_path.exists():
            raise PdfNotFoundError(pdf_path)
        if not pdf_path.is_file():
            raise InvalidPdfError(pdf_path, "path is not a file")

        try:
            document = pymupdf.open(pdf_path)
        except pymupdf.FileNotFoundError as exc:
            raise PdfNotFoundError(pdf_path) from exc
        except pymupdf.EmptyFileError as exc:
            raise InvalidPdfError(pdf_path, "file is empty") from exc
        except pymupdf.FileDataError as exc:
            raise InvalidPdfError(pdf_path, str(exc)) from exc
        except Exception as exc:
            raise InvalidPdfError(pdf_path, str(exc)) from exc

        try:
            return self._render_document(document, pdf_path, output_dir, dpi)
        finally:
            document.close()

    def _render_document(
        self,
        document: pymupdf.Document,
        pdf_path: Path,
        output_dir: Path,
        dpi: int,
    ) -> list[Page]:
        if document.page_count == 0:
            raise EmptyPdfError(pdf_path)

        output_dir.mkdir(parents=True, exist_ok=True)
        pages: list[Page] = []
        for index, page in enumerate(document):
            page_number = index + 1
            filename = page_image_filename(page_number)
            image_path = output_dir / filename
            try:
                pixmap = page.get_pixmap(dpi=dpi)
                pixmap.save(str(image_path))
            except Exception as exc:
                raise PageRenderError(page_number, str(exc)) from exc
            pages.append(
                Page(
                    page_number=page_number,
                    image=filename,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )

        metadata_path = output_dir / PAGES_METADATA_FILENAME
        metadata_path.write_text(
            json.dumps([page.model_dump(mode="json") for page in pages], indent=2),
            encoding="utf-8",
        )
        logger.info("Rendered %s page(s) from %s to %s", len(pages), pdf_path, output_dir)
        return pages
