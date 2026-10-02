"""Orchestrate exam report generation from grading.json artifacts."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.exceptions import (
    GradingNotFoundError,
    ReportPdfError,
    ReportWriteError,
    RubricNotFoundError,
)
from app.functions.artifact_guard import changed_files, snapshot_files
from app.functions.grading_artifact import load_question_grades, paired_grading_artifact_paths
from app.functions.question_names import (
    parse_question_ref,
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
from app.models.exam_schema import ExamPart, ExamSchema
from app.models.grading import QuestionGrade, Rubric
from app.models.report import (
    MISSING_UNANSWERED,
    MISSING_UNGRADED,
    ExamReport,
    PromptVersions,
    ReportMetadata,
    ReportResult,
)
from app.services.grading.rubric import RubricLoader
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
        exam_schema: ExamSchema | None = None,
        rubric_loader: RubricLoader | None = None,
        default_rubric: Callable[[int, list[ExamPart]], Rubric] | None = None,
    ) -> None:
        """``default_rubric`` (the pack's ``rubric_from_parts``) supplies the maximum
        of a question whose rubric file is missing."""
        self._reporter = reporter
        self._exam_schema = exam_schema
        self._rubrics = rubric_loader
        self._default_rubric = default_rubric
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

        question_paths = question_artifact_paths(questions_dir)
        snapshot = snapshot_files(grading_paths + question_paths)
        maximums, labels = self._expected_rows(
            question_paths, {g.question_number for g in grades}
        )
        exam = aggregate_exam_report(
            grades,
            self._metadata(questions_dir, student_id),
            expected_maximums=maximums,
            missing_labels=labels,
        )
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

    def _expected_rows(
        self, question_paths: list[Path], graded: set[int]
    ) -> tuple[dict[int, float], dict[int, str]]:
        """Maximum + label for every exam question without a grade, so it counts as 0.

        A question folder without ``grading.json`` is ``TIDAK DINILAI``; an exam
        question with no folder at all is ``TIDAK DIJAWAB``. With an answer key, a
        folder numbered outside it (a provisional number for an unnumbered crop)
        is only warned about: it has no key to be graded against.
        """
        parts_by_number = {
            q.number: list(q.parts)
            for q in (self._exam_schema.questions if self._exam_schema else [])
        }
        ungraded = {
            number
            for number in (_folder_question_number(p.parent) for p in question_paths)
            if number is not None and number not in graded
        }
        if parts_by_number:
            for number in sorted(ungraded - set(parts_by_number)):
                print_warning(
                    f"Soal {number} (nomor sementara, di luar kunci) tidak dinilai"
                )
            ungraded &= set(parts_by_number)
        maximums: dict[int, float] = {}
        labels: dict[int, str] = {}
        for number in sorted((set(parts_by_number) - graded) | ungraded):
            maximum = self._maximum_for(number, parts_by_number.get(number, []))
            if maximum is None:
                continue
            maximums[number] = maximum
            labels[number] = MISSING_UNGRADED if number in ungraded else MISSING_UNANSWERED
        return maximums, labels

    def _maximum_for(self, number: int, parts: list[ExamPart]) -> float | None:
        if self._rubrics is None:
            return None
        try:
            return self._rubrics.load(number).maximum_score
        except RubricNotFoundError as exc:
            if self._default_rubric is not None:
                print_warning(f"Soal {number}: {exc}; nilai maksimum dari rubric bawaan topik")
                return self._default_rubric(number, parts).maximum_score
            print_warning(f"Soal {number} tidak masuk nilai maksimum: {exc}")
            return None

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


def _folder_question_number(question_dir: Path) -> int | None:
    try:
        return int(parse_question_ref(question_dir.name).removeprefix("question_"))
    except ValueError:
        return None
