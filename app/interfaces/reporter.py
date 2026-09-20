from abc import ABC, abstractmethod
from pathlib import Path

from app.models.report import ExamReport


class GradeReporter(ABC):
    @abstractmethod
    def write(self, report: ExamReport, output_dir: Path) -> list[Path]:
        """Write report artifacts; return paths of files written."""
