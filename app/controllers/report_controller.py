"""Orchestrate exam report generation from grading.json artifacts."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Sequence
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
    report_html_filename,
    report_json_filename,
    split_question_ref,
    summary_csv_filename,
)
from app.functions.report_aggregate import QuestionKey, aggregate_exam_report
from app.functions.sheet_score import SheetButir, question_is_readable, sheet_report_rows
from app.functions.report_details import load_question_report_details
from app.functions.run_layout import CROPS_SUBDIR
from app.functions.validation_artifact import load_question_artifact, question_artifact_paths
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
        sheet_butir: Sequence[SheetButir] | None = None,
        total_mode: str = "sum",
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
        self._sheet_butir = tuple(sheet_butir) if sheet_butir else ()
        self._total_mode = total_mode

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
            question_paths, {(g.question_number, g.part_label) for g in grades}
        )
        metadata = self._metadata(questions_dir, student_id)
        if self._sheet_butir:
            prepared = sheet_report_rows(
                grades,
                self._sheet_butir,
                readable=self._readable_flags(question_paths),
                missing_labels=labels,
            )
            exam = aggregate_exam_report(
                grades,
                metadata,
                prepared_rows=prepared,
                total_mode=self._total_mode,
            )
        else:
            exam = aggregate_exam_report(
                grades,
                metadata,
                expected_maximums=maximums,
                missing_labels=labels,
                total_mode=self._total_mode,
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
        self, question_paths: list[Path], graded: set[QuestionKey]
    ) -> tuple[dict[QuestionKey, float], dict[QuestionKey, str]]:
        """Maximum + label for every exam (sub-)question without a grade, so it counts as 0.

        A question folder without ``grading.json`` is ``TIDAK DINILAI``; an exam
        question with no folder at all is ``TIDAK DIJAWAB``. With an answer key, a
        folder numbered outside it (a provisional number for an unnumbered crop)
        is only warned about: it has no key to be graded against.
        """
        parts_by_key: dict[QuestionKey, list[ExamPart]] = {
            (q.number, q.part_label): list(q.parts)
            for q in (self._exam_schema.questions if self._exam_schema else [])
        }
        ungraded = {
            key
            for key in (_folder_question_key(p.parent) for p in question_paths)
            if key is not None and key not in graded
        }
        if parts_by_key:
            for number, part_label in sorted(ungraded - set(parts_by_key)):
                logger.warning(
                    f"Soal {number}{part_label} (nomor sementara, di luar kunci) tidak dinilai"
                )
            ungraded &= set(parts_by_key)
        maximums: dict[QuestionKey, float] = {}
        labels: dict[QuestionKey, str] = {}
        for key in sorted((set(parts_by_key) - graded) | ungraded):
            maximum = self._maximum_for(key, parts_by_key.get(key, []))
            if maximum is None:
                continue
            maximums[key] = maximum
            labels[key] = MISSING_UNGRADED if key in ungraded else MISSING_UNANSWERED
        return maximums, labels

    def _maximum_for(self, key: QuestionKey, parts: list[ExamPart]) -> float | None:
        if self._rubrics is None:
            return None
        number, part_label = key
        try:
            return self._rubrics.load(number, part_label).maximum_score
        except RubricNotFoundError as exc:
            ref = f"{number}{part_label}"
            if self._default_rubric is not None:
                logger.warning(f"Soal {ref}: {exc}; nilai maksimum dari rubric bawaan topik")
                return self._default_rubric(number, parts).maximum_score
            logger.warning(f"Soal {ref} tidak masuk nilai maksimum: {exc}")
            return None

    @staticmethod
    def _readable_flags(question_paths: list[Path]) -> dict[QuestionKey, bool]:
        flags: dict[QuestionKey, bool] = {}
        for path in question_paths:
            key = _folder_question_key(path.parent)
            if key is None:
                continue
            try:
                flags[key] = question_is_readable(load_question_artifact(path))
            except ValueError:
                flags[key] = False
        return flags

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
            logger.warning(str(exc))
            # A PDF still open in a viewer cannot be removed; the warning already says so.
            with contextlib.suppress(OSError):
                tex_path.with_suffix(".pdf").unlink(missing_ok=True)
            return None


def _folder_question_key(question_dir: Path) -> QuestionKey | None:
    try:
        return split_question_ref(question_dir.name)
    except ValueError:
        return None
