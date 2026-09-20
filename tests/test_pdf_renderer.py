import json
from pathlib import Path

import pytest

from app.exceptions import EmptyPdfError, InvalidPdfError, PdfNotFoundError
from app.functions.page_names import page_image_filename
from app.services.pdf.renderer import PyMuPdfRenderer
from tests.helpers import write_pdf


def test_page_image_filename_is_zero_padded() -> None:
    assert page_image_filename(1) == "page_001.png"
    assert page_image_filename(12) == "page_012.png"
    assert page_image_filename(100) == "page_100.png"


def test_page_image_filename_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        page_image_filename(0)


def test_render_single_page_pdf(tmp_path: Path) -> None:
    pdf_path = write_pdf(tmp_path / "single.pdf", 1)
    output_dir = tmp_path / "pages"

    pages = PyMuPdfRenderer().render(pdf_path, output_dir, dpi=72)

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].image == "page_001.png"
    assert pages[0].width > 0
    assert pages[0].height > 0
    assert (output_dir / "page_001.png").is_file()
    assert (output_dir / "pages.json").is_file()


def test_render_multi_page_pdf(tmp_path: Path) -> None:
    pdf_path = write_pdf(tmp_path / "multi.pdf", 3)
    output_dir = tmp_path / "pages"

    pages = PyMuPdfRenderer().render(pdf_path, output_dir, dpi=72)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert [page.image for page in pages] == [
        "page_001.png",
        "page_002.png",
        "page_003.png",
    ]
    for page in pages:
        assert (output_dir / page.image).is_file()
        assert page.width > 0
        assert page.height > 0

    metadata = json.loads((output_dir / "pages.json").read_text(encoding="utf-8"))
    assert len(metadata) == 3
    assert metadata[1]["image"] == "page_002.png"


def test_render_empty_pdf_raises(tmp_path: Path) -> None:
    pdf_path = write_pdf(tmp_path / "empty.pdf", 0)
    output_dir = tmp_path / "pages"

    with pytest.raises(EmptyPdfError):
        PyMuPdfRenderer().render(pdf_path, output_dir, dpi=72)

    assert not (output_dir / "page_001.png").exists()
    assert not (output_dir / "pages.json").exists()


def test_render_invalid_file_raises(tmp_path: Path) -> None:
    pdf_path = tmp_path / "not.pdf"
    pdf_path.write_bytes(b"this is not a pdf")

    with pytest.raises(InvalidPdfError):
        PyMuPdfRenderer().render(pdf_path, tmp_path / "pages", dpi=72)


def test_render_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PdfNotFoundError):
        PyMuPdfRenderer().render(tmp_path / "missing.pdf", tmp_path / "pages", dpi=72)
