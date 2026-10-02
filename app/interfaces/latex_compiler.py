from abc import ABC, abstractmethod
from pathlib import Path


class LatexCompiler(ABC):
    @abstractmethod
    def compile(self, tex_path: Path) -> Path:
        """Compile ``tex_path`` next to itself; return the PDF path.

        Raises:
            ReportPdfError: if the PDF could not be produced.
        """
