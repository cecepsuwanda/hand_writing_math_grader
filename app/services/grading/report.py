"""Write exam report as JSON, CSV, and HTML."""

from __future__ import annotations

import csv
import logging
from io import StringIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.exceptions import ReportWriteError
from app.functions.question_names import (
    report_html_filename,
    report_json_filename,
    summary_csv_filename,
)
from app.functions.report_aggregate import summary_csv_rows
from app.interfaces.reporter import GradeReporter
from app.models.report import ExamReport

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
DEFAULT_TEMPLATE_NAME = "report.html.j2"


class JsonCsvHtmlReporter(GradeReporter):
    def __init__(
        self,
        template_dir: Path | None = None,
        template_name: str = DEFAULT_TEMPLATE_NAME,
    ) -> None:
        self._template_dir = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self._template_name = template_name

    def write(self, report: ExamReport, output_dir: Path) -> list[Path]:
        output_dir = Path(output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / report_json_filename()
            csv_path = output_dir / summary_csv_filename()
            html_path = output_dir / report_html_filename()

            json_path.write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
            csv_path.write_text(self._render_csv(report), encoding="utf-8")
            html_path.write_text(self._render_html(report), encoding="utf-8")
        except OSError as exc:
            raise ReportWriteError(str(exc)) from exc

        paths = [json_path, csv_path, html_path]
        logger.info("Wrote report artifacts under %s", output_dir)
        return paths

    def _render_csv(self, report: ExamReport) -> str:
        header, row = summary_csv_rows(report)
        buffer = StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        writer.writerow(row)
        return buffer.getvalue()

    def _render_html(self, report: ExamReport) -> str:
        try:
            env = Environment(
                loader=FileSystemLoader(str(self._template_dir)),
                autoescape=select_autoescape(["html", "xml", "j2"]),
            )
            template = env.get_template(self._template_name)
            return template.render(report=report)
        except Exception as exc:  # jinja2.TemplateError and OS errors
            raise ReportWriteError(f"HTML template failed: {exc}") from exc
