"""Write the per-student LaTeX report (crops + OCR + grading comments)."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.exceptions import ReportWriteError
from app.functions.latex_report import build_latex_report_context
from app.functions.question_names import report_tex_filename
from app.interfaces.reporter import DetailedReporter
from app.models.report import ExamReport, QuestionReportDetail

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
DEFAULT_TEMPLATE_NAME = "report.tex.j2"


def latex_jinja_environment(template_dir: Path) -> Environment:
    """Jinja delimiters that do not collide with LaTeX braces or ``%`` comments."""
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


class LatexReportWriter(DetailedReporter):
    def __init__(
        self,
        template_dir: Path | None = None,
        template_name: str = DEFAULT_TEMPLATE_NAME,
    ) -> None:
        self._template_dir = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self._template_name = template_name

    def write(
        self,
        report: ExamReport,
        details: list[QuestionReportDetail],
        output_dir: Path,
    ) -> Path:
        output_dir = Path(output_dir)
        view = build_latex_report_context(report, details, output_dir)
        try:
            template = latex_jinja_environment(self._template_dir).get_template(
                self._template_name
            )
            content = template.render(report=view)
        except Exception as exc:  # jinja2.TemplateError and OS errors
            raise ReportWriteError(f"LaTeX template failed: {exc}") from exc

        path = output_dir / report_tex_filename()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise ReportWriteError(str(exc)) from exc
        logger.info("Wrote LaTeX report %s", path)
        return path
