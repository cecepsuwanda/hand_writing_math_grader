"""End-to-end pipeline orchestration (web jobs)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from app.controllers.crop_controller import CropController
from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.latex_controller import LatexController
from app.controllers.question_review_controller import QuestionReviewController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.exceptions import (
    CropsRegionsMissingError,
    QuestionCropsInvalidError,
    QuestionsNotFoundError,
)
from app.functions.pages_artifact import (
    crops_regions_present,
    load_pages_from_dir,
    pages_missing_regions,
)
from app.functions.question_crops import (
    list_crops_in_reading_order,
    load_question_crops,
    validate_question_crops,
)
from app.functions.recognition_artifact import prune_stale_recognition
from app.functions.validation_artifact import question_artifact_paths
from app.functions.workspace_reset import (
    clear_directory_contents,
    ensure_resettable_dir,
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
        question_review: QuestionReviewController | None = None,
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
        self._question_review = question_review

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
        use_existing_crops: bool = False,
    ) -> ProcessResult:
        pdf_path = Path(pdf_path)
        pages_dir = Path(pages_dir)
        recognition_dir = Path(recognition_dir)
        questions_dir = Path(questions_dir)
        output_dir = Path(output_dir)

        if reset_workspace:
            # Guessing the run root (e.g. from a custom --output) could wipe the wrong folder.
            if workspace_root is None:
                raise ValueError("reset_workspace=True requires workspace_root")
            root = Path(workspace_root)
            removed = prepare_pipeline_workspace(
                root,
                pages_dir=pages_dir,
                recognition_dir=recognition_dir,
                questions_dir=questions_dir,
                crops_dir=self._resolve_crops_dir(crops_dir) if use_existing_crops else crops_dir,
                keep_crops=use_existing_crops,
            )
            if self._on_output_cleared is not None:
                self._on_output_cleared(root, removed)

        render_result = self._render.render(pdf_path, pages_dir, dpi)
        self._emit(ProcessStage.RENDER)

        from_crops = False
        if self._crop is not None:
            self._crop.ensure_crops(
                render_result.pages,
                pages_dir,
                use_existing=use_existing_crops,
            )
            from_crops = True
            self._check_question_crops(self._crop.crops_dir if crops_dir is None else Path(crops_dir))

        self._recognize_and_extract(
            render_result.pages,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            from_crops=from_crops,
        )
        return self._run_from_questions(
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            output_dir=output_dir,
            student_id=student_id,
            crops_dir=crops_dir,
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
        workspace_root: Path | None = None,
    ) -> ProcessResult:
        """Continue pipeline from existing page images + regions crops (no re-ink).

        Prior recognition/questions are replaced only after recognition succeeds,
        so a failed rerun keeps them. With ``workspace_root`` both dirs must lie
        inside it (or be empty) before anything runs.
        """
        crops = self.transcribe_from_crops(
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            crops_dir=crops_dir,
            workspace_root=workspace_root,
        )
        return self._run_from_questions(
            pages_dir=Path(pages_dir),
            recognition_dir=Path(recognition_dir),
            questions_dir=Path(questions_dir),
            output_dir=Path(output_dir),
            student_id=student_id,
            crops_dir=crops,
        )

    def transcribe_from_crops(
        self,
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        crops_dir: Path | None = None,
        workspace_root: Path | None = None,
    ) -> Path | None:
        """Recognize the approved crops and write ``question.json`` files, then stop.

        Same guards and artifact replacement as :meth:`process_from_crops`, so the
        user can review ``question.json`` before grading. Returns the crops dir used.
        """
        pages_dir = Path(pages_dir)
        recognition_dir = Path(recognition_dir)
        questions_dir = Path(questions_dir)
        crops = self._resolve_crops_dir(crops_dir)

        if workspace_root is not None:
            ensure_resettable_dir(recognition_dir, run_root=workspace_root, label="recognition")
            ensure_resettable_dir(questions_dir, run_root=workspace_root, label="questions")

        if crops is not None:
            if not crops_regions_present(crops):
                raise CropsRegionsMissingError(crops)
            self._check_question_crops(crops)

        # Load pages first so a broken pages/ does not cost the prior artifacts.
        pages = load_pages_from_dir(pages_dir)
        if crops is not None and pages_missing_regions(crops, [p.page_number for p in pages]):
            raise CropsRegionsMissingError(crops)

        self._recognize_and_extract(
            pages,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            from_crops=True,
            replace_artifacts=True,
        )
        return crops

    def process_from_questions(
        self,
        *,
        questions_dir: Path,
        output_dir: Path,
        pages_dir: Path,
        recognition_dir: Path,
        student_id: str = DEFAULT_STUDENT_ID,
        crops_dir: Path | None = None,
    ) -> ProcessResult:
        """Continue from existing (possibly user-edited) question.json; never rewrites them."""
        questions_dir = Path(questions_dir)
        if not question_artifact_paths(questions_dir):
            raise QuestionsNotFoundError(questions_dir)
        if self._question_review is not None:
            self._question_review.prune_stale_latex_sources(questions_dir)
        return self._run_from_questions(
            pages_dir=Path(pages_dir),
            recognition_dir=Path(recognition_dir),
            questions_dir=questions_dir,
            output_dir=Path(output_dir),
            student_id=student_id,
            crops_dir=Path(crops_dir) if crops_dir is not None else None,
        )

    def _recognize_and_extract(
        self,
        pages: list[Page],
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        from_crops: bool,
        replace_artifacts: bool = False,
    ) -> None:
        """Recognize Ã¢â€ â€™ extract.

        ``replace_artifacts`` drops recognition of pages no longer present and
        empties ``questions_dir`` after recognition, so a shorter rerun cannot
        grade leftovers.
        """
        self._recognize.recognize_pages(
            pages, pages_dir, recognition_dir, from_crops=from_crops
        )
        if replace_artifacts:
            prune_stale_recognition(recognition_dir, [p.page_number for p in pages])
            clear_directory_contents(questions_dir)
        self._emit(ProcessStage.RECOGNIZE)

        self._extract.extract(
            recognition_dir=recognition_dir,
            output_dir=questions_dir,
            force_recognize=False,
        )
        self._emit(ProcessStage.EXTRACT)

    def _run_from_questions(
        self,
        *,
        pages_dir: Path,
        recognition_dir: Path,
        questions_dir: Path,
        output_dir: Path,
        student_id: str,
        crops_dir: Path | None,
    ) -> ProcessResult:
        """(review) Ã¢â€ â€™ LaTeX Ã¢â€ â€™ validate Ã¢â€ â€™ grade Ã¢â€ â€™ report."""
        if self._question_review is not None:
            self._question_review.require_valid(questions_dir)

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
                    question_id=row.question_id,
                    question_number=row.question_number,
                    score=row.score,
                    maximum_score=row.maximum_score,
                    review_status=row.review_status,
                    missing=row.missing,
                    missing_label=row.missing_label,
                )
                for row in exam.questions
            ],
            total_score=exam.total_score,
            maximum_total=exam.maximum_total,
            overall_status=exam.overall_status,
            output_dir=output_dir,
            report_json_path=report_result.report_json_path,
            summary_csv_path=report_result.summary_csv_path,
            report_html_path=report_result.report_html_path,
            report_tex_path=report_result.report_tex_path,
            report_pdf_path=report_result.report_pdf_path,
            questions_dir=questions_dir,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
        )

    def _resolve_crops_dir(self, crops_dir: Path | None) -> Path | None:
        if crops_dir is not None:
            return Path(crops_dir)
        if self._crop is not None:
            return self._crop.crops_dir
        return None

    def _report_crops_dir(self, crops_dir: Path | None) -> Path | None:
        return self._resolve_crops_dir(crops_dir)

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
        try:
            known = [crop.name for crop in list_crops_in_reading_order(crops_dir)]
        except ValueError as exc:
            raise QuestionCropsInvalidError([str(exc)]) from exc
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
