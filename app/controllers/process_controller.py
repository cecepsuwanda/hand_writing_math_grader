"""End-to-end pipeline orchestration (CLI process)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from app.controllers.crop_controller import CropController
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
from app.services.workspace.cleaner import (
    clear_directory_contents,
    prepare_pipeline_workspace,
)

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
        crop_controller: CropController | None = None,
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
        self._crop = crop_controller
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
        force_yes: bool = False,
        use_existing_crops: bool = False,
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

        from_crops = False
        if self._crop is not None:
            self._crop.ensure_crops_confirmed(
                render_result.pages,
                pages_dir,
                use_existing=use_existing_crops,
                force_yes=force_yes,
            )
            from_crops = True

        self._recognize.recognize_pages(
            render_result.pages,
            pages_dir,
            recognition_dir,
            from_crops=from_crops,
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

    def process_from_crops(
        self,
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        output_dir: Path,
        student_id: str = "student_001",
        crops_dir: Path | None = None,
    ) -> ProcessResult:
        """Continue pipeline from existing page images + regions crops (no re-ink)."""
        from app.functions.pages_artifact import crops_regions_present, load_pages_from_dir
        from app.exceptions import MathGraderError

        pages_dir = Path(pages_dir)
        recognition_dir = Path(recognition_dir)
        questions_dir = Path(questions_dir)
        output_dir = Path(output_dir)
        crops = Path(crops_dir) if crops_dir is not None else None

        if crops is not None and not crops_regions_present(crops):
            raise MathGraderError(
                f"No page_*_regions.json under {crops}. "
                "Run menu 2 (crop ink) or 3 (recrop) first."
            )

        # Drop prior recognition/questions so a shorter rerun cannot grade leftovers.
        # Pages, crops, and standards stay.
        clear_directory_contents(recognition_dir)
        clear_directory_contents(questions_dir)

        pages = load_pages_from_dir(pages_dir)
        self._recognize.recognize_pages(
            pages,
            pages_dir,
            recognition_dir,
            from_crops=True,
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
            "Process-from-crops complete for %s: %s/%s %s",
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
