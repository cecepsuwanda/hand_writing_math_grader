from __future__ import annotations

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


class FakeClient:
    """Vision/reasoning client double: fixed content or a FIFO queue of responses."""

    def __init__(self, content: str | list[str]) -> None:
        if isinstance(content, list):
            self._queue = list(content)
            self.content = content[0] if content else ""
        else:
            self._queue = None
            self.content = content
        self.calls: list[tuple[str, Path, str]] = []
        self.text_calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, model: str) -> str:
        self.text_calls.append((prompt, model))
        if self._queue is not None:
            if not self._queue:
                raise AssertionError("FakeClient exhausted response queue")
            return self._queue.pop(0)
        return self.content

    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        self.calls.append((prompt, image_path, model))
        if self._queue is not None:
            if not self._queue:
                raise AssertionError("FakeClient exhausted response queue")
            return self._queue.pop(0)
        return self.content
