from abc import ABC, abstractmethod
from pathlib import Path

from app.models.page import Page


class PdfRenderer(ABC):
    @abstractmethod
    def render(self, pdf_path: Path, output_dir: Path, dpi: int) -> list[Page]:
        """Render each PDF page to PNG and return page metadata."""
