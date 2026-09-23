"""End-to-end pipeline orchestration (CLI process)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.latex_controller import LatexController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.models.process import (
    PROCESS_STAGES,
    ProcessProgress,
    ProcessResult,
    ProcessStage,
    QuestionScoreSummary,
)
from app.services.workspace.cleaner import prepare_pipeline_workspace

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProcessProgress], None]
ClearedCallback = Callable[[Path, list[str]], None]


class ProcessController:
    def __init__(
        self,
        *,
        render_controller: RenderController,
        recognize_controller: RecognizeController,
        extract_controller: ExtractController,
        latex_controller: LatexController,
        validate_controller: ValidateController,
        grade_controller: GradeController,
        report_controller: ReportController,
        on_progress: ProgressCallback | None = None,
        on_output_cleared: ClearedCallback | None = None,
    ) -> None:
        self._render = render_controller
        self._recognize = recognize_controller
        self._extract = extract_controller
        self._latex = latex_controller
        self._validate = validate_controller
        self._grade = grade_controller
        self._report = report_controller
        self._on_progress = on_progress
        self._on_output_cleared = on_output_cleared

    def process(
        self,
        pdf_path: Path,
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        output_dir: Path,
        dpi: int,
        student_id: str = "student_001",
        workspace_root: Path | None = None,
        reset_workspace: bool = True,
        crops_dir: Path | None = None,
    ) -> ProcessResult:
        pdf_path = Path(pdf_path)
        pages_dir = Path(pages_dir)
        recognition_dir = Path(recognition_dir)
        questions_dir = Path(questions_dir)
        output_dir = Path(output_dir)

        if reset_workspace:
            root = Path(workspace_root) if workspace_root is not None else output_dir
            removed = prepare_pipeline_workspace(
                root,
                pages_dir=pages_dir,
                recognition_dir=recognition_dir,
                questions_dir=questions_dir,
                crops_dir=crops_dir,
            )
            if self._on_output_cleared is not None:
                self._on_output_cleared(root, removed)

        render_result = self._render.render(pdf_path, pages_dir, dpi)
        self._emit(ProcessStage.RENDER, 1)

        self._recognize.recognize_pages(
            render_result.pages, pages_dir, recognition_dir
        )
        self._emit(ProcessStage.RECOGNIZE, 2)

        self._extract.extract(
            recognition_dir=recognition_dir,
            output_dir=questions_dir,
            force_recognize=False,
        )
        self._emit(ProcessStage.EXTRACT, 3)

        self._latex.build(questions_dir)
        self._emit(ProcessStage.LATEX, 4)

        self._validate.validate(questions_dir)
        self._emit(ProcessStage.VALIDATE, 5)

        grade_result = self._grade.grade(questions_dir)
        self._emit(ProcessStage.GRADE, 6)

        report_result = self._report.report(
            questions_dir,
            output_dir,
            student_id=student_id,
        )
        self._emit(ProcessStage.REPORT, 7)

        questions = [
            QuestionScoreSummary(
                question_id=g.question_id,
                question_number=g.question_number,
                score=g.score,
                maximum_score=g.maximum_score,
                review_status=g.review_status,
            )
            for g in grade_result.grades
        ]
        total = report_result.exam_report.total_score
        maximum = report_result.exam_report.maximum_total
        overall = report_result.exam_report.overall_status

        logger.info(
            "Process complete for %s: %s/%s %s",
            student_id,
            total,
            maximum,
            overall.value,
        )
        return ProcessResult(
            student_id=student_id,
            questions=questions,
            total_score=total,
            maximum_total=maximum,
            overall_status=overall,
            output_dir=output_dir,
            report_json_path=report_result.report_json_path,
            summary_csv_path=report_result.summary_csv_path,
            report_html_path=report_result.report_html_path,
            questions_dir=questions_dir,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
        )

    def _emit(self, stage: ProcessStage, completed: int) -> None:
        if self._on_progress is None:
            return
        self._on_progress(
            ProcessProgress(
                stage=stage,
                completed=completed,
                total=len(PROCESS_STAGES),
            )
        )
