from pathlib import Path

import pymupdf

# PyMuPDF refuses to save a document with zero pages, so keep a minimal PDF.
_EMPTY_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)


def write_pdf(path: Path, page_count: int) -> Path:
    if page_count < 0:
        raise ValueError("page_count must be >= 0")
    if page_count == 0:
        path.write_bytes(_EMPTY_PDF)
        return path

    document = pymupdf.open()
    for _ in range(page_count):
        document.new_page()
    document.save(path)
    document.close()
    return path
