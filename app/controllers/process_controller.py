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
from app.exceptions import CropsRegionsMissingError, QuestionCropsInvalidError
from app.functions.pages_artifact import crops_regions_present, load_pages_from_dir
from app.functions.question_crops import (
    list_crops_in_reading_order,
    load_question_crops,
    validate_question_crops,
)
from app.functions.workspace_reset import (
    clear_directory_contents,
    prepare_pipeline_workspace,
)
from app.models.defaults import DEFAULT_STUDENT_ID
from app.models.grading import GradeResult
from app.models.page import Page
from app.models.process import (
    PROCESS_STAGES,
    ProcessProgress,
    ProcessResult,
    ProcessStage,
    QuestionScoreSummary,
)
from app.models.report import ReportResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProcessProgress], None]
ClearedCallback = Callable[[Path, list[str]], None]
QuestionCropsMissingCallback = Callable[[Path], None]


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
        question_numbers: list[int] | None = None,
        on_question_crops_missing: QuestionCropsMissingCallback | None = None,
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
        self._question_numbers = list(question_numbers or [])
        self._on_question_crops_missing = on_question_crops_missing

    def process(
        self,
        pdf_path: Path,
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        output_dir: Path,
        dpi: int,
        student_id: str = DEFAULT_STUDENT_ID,
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
        self._emit(ProcessStage.RENDER)

        from_crops = False
        if self._crop is not None:
            self._crop.ensure_crops_confirmed(
                render_result.pages,
                pages_dir,
                use_existing=use_existing_crops,
                force_yes=force_yes,
            )
            from_crops = True
            self._check_question_crops(
                Path(crops_dir) if crops_dir is not None else self._crop.crops_dir
            )

        return self._run_from_recognition(
            render_result.pages,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            output_dir=output_dir,
            student_id=student_id,
            crops_dir=crops_dir,
            from_crops=from_crops,
        )

    def process_from_crops(
        self,
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        output_dir: Path,
        student_id: str = DEFAULT_STUDENT_ID,
        crops_dir: Path | None = None,
    ) -> ProcessResult:
        """Continue pipeline from existing page images + regions crops (no re-ink)."""
        pages_dir = Path(pages_dir)
        recognition_dir = Path(recognition_dir)
        questions_dir = Path(questions_dir)
        crops = Path(crops_dir) if crops_dir is not None else None

        if crops is not None:
            if not crops_regions_present(crops):
                raise CropsRegionsMissingError(crops)
            self._check_question_crops(crops)

        # Load pages first so a broken pages/ does not cost the prior artifacts.
        pages = load_pages_from_dir(pages_dir)

        # Drop prior recognition/questions so a shorter rerun cannot grade leftovers.
        # Pages, crops, and standards stay.
        clear_directory_contents(recognition_dir)
        clear_directory_contents(questions_dir)

        return self._run_from_recognition(
            pages,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            output_dir=Path(output_dir),
            student_id=student_id,
            crops_dir=crops,
            from_crops=True,
        )

    def _run_from_recognition(
        self,
        pages: list[Page],
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        output_dir: Path,
        student_id: str,
        crops_dir: Path | None,
        from_crops: bool,
    ) -> ProcessResult:
        """Recognize → extract → LaTeX → validate → grade → report."""
        self._recognize.recognize_pages(
            pages, pages_dir, recognition_dir, from_crops=from_crops
        )
        self._emit(ProcessStage.RECOGNIZE)

        self._extract.extract(
            recognition_dir=recognition_dir,
            output_dir=questions_dir,
            force_recognize=False,
        )
        self._emit(ProcessStage.EXTRACT)

        self._latex.build(questions_dir)
        self._emit(ProcessStage.LATEX)

        self._validate.validate(questions_dir)
        self._emit(ProcessStage.VALIDATE)

        grade_result = self._grade.grade(questions_dir)
        self._emit(ProcessStage.GRADE)

        report_result = self._report.report(
            questions_dir,
            output_dir,
            student_id=student_id,
            crops_dir=self._report_crops_dir(crops_dir),
        )
        self._emit(ProcessStage.REPORT)

        result = self._build_result(
            grade_result,
            report_result,
            student_id=student_id,
            output_dir=output_dir,
            questions_dir=questions_dir,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
        )
        logger.info(
            "Process complete for %s: %s/%s %s",
            student_id,
            result.total_score,
            result.maximum_total,
            result.overall_status.value,
        )
        return result

    @staticmethod
    def _build_result(
        grade_result: GradeResult,
        report_result: ReportResult,
        *,
        student_id: str,
        output_dir: Path,
        questions_dir: Path,
        pages_dir: Path,
        recognition_dir: Path,
    ) -> ProcessResult:
        exam = report_result.exam_report
        return ProcessResult(
            student_id=student_id,
            questions=[
                QuestionScoreSummary(
                    question_id=g.question_id,
                    question_number=g.question_number,
                    score=g.score,
                    maximum_score=g.maximum_score,
                    review_status=g.review_status,
                )
                for g in grade_result.grades
            ],
            total_score=exam.total_score,
            maximum_total=exam.maximum_total,
            overall_status=exam.overall_status,
            output_dir=output_dir,
            report_json_path=report_result.report_json_path,
            summary_csv_path=report_result.summary_csv_path,
            report_html_path=report_result.report_html_path,
            report_tex_path=report_result.report_tex_path,
            questions_dir=questions_dir,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
        )

    def _report_crops_dir(self, crops_dir: Path | None) -> Path | None:
        if crops_dir is not None:
            return Path(crops_dir)
        if self._crop is not None:
            return self._crop.crops_dir
        return None

    def _check_question_crops(self, crops_dir: Path) -> None:
        """Validate user question_crops, or warn that the model will guess numbers."""
        try:
            mapping = load_question_crops(crops_dir)
        except ValueError as exc:
            raise QuestionCropsInvalidError([str(exc)]) from exc
        if mapping is None:
            if self._on_question_crops_missing is not None:
                self._on_question_crops_missing(crops_dir)
            return
        known = [crop.name for crop in list_crops_in_reading_order(crops_dir)]
        report = validate_question_crops(mapping, self._question_numbers, known)
        if not report.ok:
            raise QuestionCropsInvalidError(report.errors)

    def _emit(self, stage: ProcessStage) -> None:
        if self._on_progress is None:
            return
        self._on_progress(
            ProcessProgress(
                stage=stage,
                completed=PROCESS_STAGES.index(stage) + 1,
                total=len(PROCESS_STAGES),
            )
        )
