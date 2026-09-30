from abc import ABC, abstractmethod
from pathlib import Path

from app.models.report import ExamReport, QuestionReportDetail


class GradeReporter(ABC):
    @abstractmethod
    def write(self, report: ExamReport, output_dir: Path) -> list[Path]:
        """Write report artifacts; return paths of files written."""


class DetailedReporter(ABC):
    @abstractmethod
    def write(
        self,
        report: ExamReport,
        details: list[QuestionReportDetail],
        output_dir: Path,
    ) -> Path:
        """Write one per-question detailed report; return its path."""
