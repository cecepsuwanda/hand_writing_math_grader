"""Orchestrate exam report generation from grading.json artifacts."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.exceptions import GradingNotFoundError, ReportPdfError, ReportWriteError
from app.functions.artifact_guard import changed_files, snapshot_files
from app.functions.grading_artifact import load_question_grades, paired_grading_artifact_paths
from app.functions.question_names import (
    report_html_filename,
    report_json_filename,
    summary_csv_filename,
)
from app.functions.report_aggregate import aggregate_exam_report
from app.functions.report_details import load_question_report_details
from app.functions.run_layout import CROPS_SUBDIR
from app.functions.validation_artifact import question_artifact_paths
from app.interfaces.latex_compiler import LatexCompiler
from app.interfaces.reporter import DetailedReporter, GradeReporter
from app.models.defaults import DEFAULT_STUDENT_ID
from app.models.grading import QuestionGrade
from app.models.report import ExamReport, PromptVersions, ReportMetadata, ReportResult
from app.views.error_view import print_warning

logger = logging.getLogger(__name__)


class ReportController:
    def __init__(
        self,
        reporter: GradeReporter,
        *,
        standard_dir: Path,
        vision_model: str = "",
        reasoning_model: str = "",
        prompt_versions: PromptVersions | None = None,
        latex_reporter: DetailedReporter | None = None,
        pdf_compiler: LatexCompiler | None = None,
    ) -> None:
        self._reporter = reporter
        self._standard_dir = Path(standard_dir)
        self._vision_model = vision_model
        self._reasoning_model = reasoning_model
        self._prompt_versions = prompt_versions or PromptVersions()
        self._latex_reporter = latex_reporter
        self._pdf_compiler = pdf_compiler

    def report(
        self,
        questions_dir: Path,
        output_dir: Path,
        *,
        student_id: str = DEFAULT_STUDENT_ID,
        crops_dir: Path | None = None,
    ) -> ReportResult:
        questions_dir = Path(questions_dir)
        output_dir = Path(output_dir)
        grading_paths = paired_grading_artifact_paths(questions_dir)
        if not grading_paths:
            raise GradingNotFoundError(questions_dir)
        grades = self._load_grades(grading_paths)

        snapshot = snapshot_files(grading_paths + question_artifact_paths(questions_dir))
        exam = aggregate_exam_report(grades, self._metadata(questions_dir, student_id))
        written = self._reporter.write(exam, output_dir)
        tex_path = self._write_latex(
            exam,
            questions_dir,
            output_dir,
            crops_dir if crops_dir is not None else questions_dir.parent / CROPS_SUBDIR,
        )
        modified = changed_files(snapshot)
        if modified:
            raise ReportWriteError(
                f"source artifact was modified during report: {modified[0]}"
            )
        pdf_path = self._compile_pdf(tex_path)

        by_name = {p.name: p for p in written}
        result = ReportResult(
            exam_report=exam,
            output_dir=output_dir,
            report_json_path=by_name.get(
                report_json_filename(), output_dir / report_json_filename()
            ),
            summary_csv_path=by_name.get(
                summary_csv_filename(), output_dir / summary_csv_filename()
            ),
            report_html_path=by_name.get(
                report_html_filename(), output_dir / report_html_filename()
            ),
            report_tex_path=tex_path,
            report_pdf_path=pdf_path,
        )
        logger.info(
            "Reported %s question(s) for %s -> %s",
            len(grades),
            student_id,
            output_dir,
        )
        return result

    @staticmethod
    def _load_grades(paths: list[Path]) -> list[QuestionGrade]:
        try:
            return load_question_grades(paths)
        except ValueError as exc:
            raise ReportWriteError(str(exc)) from exc

    def _metadata(self, questions_dir: Path, student_id: str) -> ReportMetadata:
        return ReportMetadata(
            generated_at=datetime.now(timezone.utc).isoformat(),
            standard_dir=self._standard_dir,
            questions_dir=questions_dir,
            student_id=student_id,
            vision_model=self._vision_model,
            reasoning_model=self._reasoning_model,
            prompt_versions=self._prompt_versions,
        )

    def _write_latex(
        self,
        exam: ExamReport,
        questions_dir: Path,
        output_dir: Path,
        crops_dir: Path,
    ) -> Path | None:
        if self._latex_reporter is None:
            return None
        try:
            details = load_question_report_details(questions_dir, crops_dir)
        except ValueError as exc:
            raise ReportWriteError(str(exc)) from exc
        return self._latex_reporter.write(exam, details, output_dir)

    def _compile_pdf(self, tex_path: Path | None) -> Path | None:
        """PDF failure only warns: report.tex and the other reports are already written.

        A ``report.pdf`` left from an earlier run is removed on failure so it is not
        mistaken for the current report.
        """
        if self._pdf_compiler is None or tex_path is None:
            return None
        try:
            return self._pdf_compiler.compile(tex_path)
        except ReportPdfError as exc:
            print_warning(str(exc))
            # A PDF still open in a viewer cannot be removed; the warning already says so.
            with contextlib.suppress(OSError):
                tex_path.with_suffix(".pdf").unlink(missing_ok=True)
            return None
