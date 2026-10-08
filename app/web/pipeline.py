"""Use-cases behind the web pages: session-aware, prompt-free, returns models.

Builders are looked up on :mod:`app.services.pipeline_factory` at call time so
tests patch a single target, whichever page triggers them.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from app.config import AppConfig, require_vision_model
from app.controllers.crop_controller import CropController
from app.controllers.process_controller import ProcessController
from app.controllers.question_label_controller import QuestionLabelController
from app.exceptions import ArtifactNotFoundError, QuestionArtifactsInvalidError
from app.functions.grading_artifact import load_question_grade, paired_grading_artifact_paths
from app.functions.pages_artifact import crops_regions_present, load_pages_from_dir
from app.functions.paths import (
    list_jawaban_pdfs,
    list_kunci_tex,
    shorten_pdf_name,
    student_id_from_pdf_stem,
)
from app.functions.question_crops import (
    crop_to_questions,
    list_crops_in_reading_order,
    load_question_crops,
    mapping_from_crop_labels,
    question_crops_dir,
)
from app.functions.question_names import grading_filename, parse_question_ref
from app.functions.regions_artifact import crop_paths_for
from app.functions.report_artifact import load_exam_report
from app.functions.run_layout import RunLayout, layout_for_pdf, list_run_dirs, safe_run_name
from app.functions.standard_extract import exam_schema_path
from app.functions.standards_layout import topic_standard_dir
from app.functions.validation_artifact import question_artifact_paths
from app.interfaces.topic_pack import TopicPack
from app.models.exam_schema import ExamQuestion
from app.models.grading import QuestionGrade
from app.models.page import Page
from app.models.process import ProcessResult
from app.models.question import Question
from app.models.question_crops import QuestionCropsReport, QuestionLabelResult
from app.models.question_review import QuestionReviewResult
from app.models.standards import IngestKunciResult
from app.services import pipeline_factory
from app.services.math.preview import symbolic_preview_latex
from app.topics.registry import list_packs
from app.web import files
from app.web.jobs import JobReporter
from app.web.schemas import (
    CropEditorView,
    DashboardView,
    LabelRow,
    LabelView,
    PageRegionsIn,
    PageRegionsOut,
    PdfEntry,
    PreviewOut,
    QuestionResult,
    ResultsView,
    RunSteps,
    RunSummary,
    TopicOption,
)
from app.web.session import WebSession

_CLOUD_SUFFIX = "-cloud"


class WebPipeline:
    def __init__(self, session: WebSession) -> None:
        self._session = session

    @property
    def config(self) -> AppConfig:
        return self._session.config

    # --- dashboard ------------------------------------------------------------

    def dashboard(self) -> DashboardView:
        config = self.config
        active = self._session.pack
        run_names = {p.name for p in list_run_dirs(config.output.root_dir)}
        models = [config.ollama.vision_model, config.ollama.reasoning_model]
        return DashboardView(
            topics=[
                TopicOption(
                    id=pack.id,
                    label=pack.label,
                    active=pack.id == active.id,
                    standard_ready=self._standard_ready(pack.id),
                )
                for pack in list_packs()
            ],
            active_topic_id=active.id,
            active_topic_label=active.label,
            standard_dir=str(self._standard_dir()),
            standard_ready=self._standard_ready(active.id),
            kunci_files=[p.name for p in list_kunci_tex(config.input.kunci_jawaban_dir)],
            pdfs=[
                PdfEntry(
                    name=pdf.name,
                    short_name=shorten_pdf_name(pdf),
                    run_name=safe_run_name(pdf),
                    has_run=safe_run_name(pdf) in run_names,
                )
                for pdf in list_jawaban_pdfs(config.input.jawaban_dir)
            ],
            runs=[self._summary(RunLayout(root=root)) for root in list_run_dirs(config.output.root_dir)],
            vision_model=config.ollama.vision_model,
            reasoning_model=config.ollama.reasoning_model,
            cloud_models=[m for m in models if m.strip().endswith(_CLOUD_SUFFIX)],
        )

    def select_topic(self, topic_id: str) -> TopicPack:
        return self._session.select_topic(topic_id)

    # --- inputs ---------------------------------------------------------------

    def upload_kunci(self, filename: str, data: bytes) -> Path:
        return files.save_upload(
            self.config.input.kunci_jawaban_dir,
            filename,
            data,
            suffix=".tex",
            max_mb=self.config.web.max_upload_mb,
        )

    def upload_pdf(self, filename: str, data: bytes) -> Path:
        return files.save_upload(
            self.config.input.jawaban_dir,
            filename,
            data,
            suffix=".pdf",
            max_mb=self.config.web.max_upload_mb,
        )

    def ingest(self, kunci_name: str) -> IngestKunciResult:
        config = self.config
        kunci_dir = config.input.kunci_jawaban_dir
        kunci = files.require_input_file(kunci_dir, kunci_name, suffix=".tex")
        topic_id = self._session.topic_id
        standard = pipeline_factory.resolve_standard_dir(config, topic_id=topic_id)
        controller = pipeline_factory.build_ingest_kunci_controller(
            config, standard, topic_id=topic_id
        )
        return controller.ingest(kunci_path=kunci, kunci_dir=kunci_dir, standard_dir=standard)

    # --- runs -----------------------------------------------------------------

    def run(self, run_name: str) -> RunLayout:
        return files.require_run(self.config.output.root_dir, run_name)

    def run_summary(self, run_name: str) -> RunSummary:
        return self._summary(self.run(run_name))

    def run_name_for_pdf(self, pdf_name: str) -> str:
        pdf = files.require_input_file(self.config.input.jawaban_dir, pdf_name, suffix=".pdf")
        return safe_run_name(pdf)

    def propose_crops(self, pdf_name: str, reporter: JobReporter) -> RunLayout:
        """Empty this PDF's run folder, render it, and propose ink boxes."""
        config = self.config
        pdf = files.require_input_file(config.input.jawaban_dir, pdf_name, suffix=".pdf")
        layout = layout_for_pdf(config.output.root_dir, pdf)
        removed = pipeline_factory.prepare_run_workspace(layout)
        if removed:
            reporter.message(f"Folder run dikosongkan: {', '.join(removed)}")
        crop = pipeline_factory.build_crop_controller(
            config, layout.recognition_dir, crops_dir=layout.crops_dir
        )
        reporter.message(f"Render {pdf.name} ({config.pdf.dpi} dpi) + usulan kotak tinta")
        result = crop.propose_for_pdf(pdf, layout.pages_dir, config.pdf.dpi)
        boxes = sum(len(page.crop_paths) for page in result.pages)
        reporter.message(f"{len(result.pages)} halaman, {boxes} kotak crop")
        return layout

    # --- crop editor ----------------------------------------------------------

    def crop_editor(self, run_name: str, page_number: int | None = None) -> CropEditorView:
        layout = self.run(run_name)
        crop = self._crop_controller(layout)
        pages = [
            crop.load_page_regions(page.page_number, layout.pages_dir)
            for page in self._pages(layout)
        ]
        wanted = pages[0].page_number if page_number is None else page_number
        current = next((p for p in pages if p.page_number == wanted), None)
        if current is None:
            raise ArtifactNotFoundError(f"halaman {page_number} di run {layout.name}")
        return CropEditorView(
            run=layout.name,
            pages=pages,
            current=current,
            crop_names=self._crop_names(layout, current.page_number, len(current.regions)),
        )

    def page_regions(self, run_name: str, page_number: int) -> PageRegionsOut:
        layout = self.run(run_name)
        page = self._crop_controller(layout).load_page_regions(page_number, layout.pages_dir)
        return PageRegionsOut(
            page=page, crop_names=self._crop_names(layout, page_number, len(page.regions))
        )

    def save_page_regions(
        self, run_name: str, page_number: int, boxes: PageRegionsIn
    ) -> PageRegionsOut:
        layout = self.run(run_name)
        crop = self._crop_controller(layout)
        crop.save_page_regions(
            page_number,
            [box.to_detected(order) for order, box in enumerate(boxes.regions)],
            layout.pages_dir,
        )
        return self.page_regions(run_name, page_number)

    # --- question numbers -----------------------------------------------------

    def label_view(self, run_name: str) -> LabelView:
        layout = self.run(run_name)
        controller = self._label_controller(layout)
        report = None
        if question_crops_dir(layout.crops_dir).is_dir():
            report = controller.reload_all().report
        return self._label_view(layout, controller.exam_questions, report)

    def detect_labels(self, run_name: str, reporter: JobReporter) -> QuestionLabelResult:
        layout = self.run(run_name)
        controller = self._label_controller(layout)
        reporter.message("Membaca nomor soal di setiap crop")
        result = controller.label_all()
        reporter.message(
            f"Sumber: {result.source.value}; "
            f"{len(result.report.errors)} error, {len(result.report.unassigned_crops)} crop tanpa soal"
        )
        return result

    def save_labels(self, run_name: str, labels: dict[str, list[int]]) -> LabelView:
        layout = self.run(run_name)
        controller = self._label_controller(layout)
        numbers = [q.number for q in controller.exam_questions]
        mapping = mapping_from_crop_labels(
            list_crops_in_reading_order(layout.crops_dir), labels, numbers
        )
        result = controller.save_mapping(mapping)
        view = self._label_view(layout, controller.exam_questions, result.report)
        return view.model_copy(update={"saved": True})

    # --- transcription review -------------------------------------------------

    def review(self, run_name: str) -> QuestionReviewResult:
        layout = self.run(run_name)
        return pipeline_factory.build_question_review_controller(self.config).collect(
            layout.questions_dir
        )

    def save_question(self, run_name: str, payload: dict) -> QuestionReviewResult:
        layout = self.run(run_name)
        try:
            question = Question.model_validate(payload)
        except ValidationError as exc:
            raise QuestionArtifactsInvalidError([_validation_summary(exc)]) from exc
        controller = pipeline_factory.build_question_review_controller(self.config)
        return controller.save_question(layout.questions_dir, question)

    @staticmethod
    def preview(text: str) -> PreviewOut:
        return PreviewOut(latex=symbolic_preview_latex(text))

    # --- recognition + grading ------------------------------------------------

    def transcribe(self, run_name: str, reporter: JobReporter) -> None:
        """Recognize approved crops into question.json, stopping before grading."""
        require_vision_model(self.config)
        layout = self.run(run_name)
        controller = self._process_controller(layout, reporter)
        controller.transcribe_from_crops(
            pages_dir=layout.pages_dir,
            recognition_dir=layout.recognition_dir,
            questions_dir=layout.questions_dir,
            crops_dir=layout.crops_dir,
            workspace_root=layout.root,
        )

    def finish(self, run_name: str, reporter: JobReporter) -> ProcessResult:
        """Recognize â†’ grade â†’ report from the approved crops, without a review stop."""
        require_vision_model(self.config)
        layout = self.run(run_name)
        return self._process_controller(layout, reporter).process_from_crops(
            pages_dir=layout.pages_dir,
            recognition_dir=layout.recognition_dir,
            questions_dir=layout.questions_dir,
            output_dir=layout.report_dir,
            student_id=student_id_from_pdf_stem(layout.name),
            crops_dir=layout.crops_dir,
            workspace_root=layout.root,
        )

    def finish_questions(self, run_name: str, reporter: JobReporter) -> ProcessResult:
        """LaTeX â†’ validate â†’ grade â†’ report from the reviewed question.json files."""
        layout = self.run(run_name)
        return self._process_controller(layout, reporter).process_from_questions(
            questions_dir=layout.questions_dir,
            output_dir=layout.report_dir,
            pages_dir=layout.pages_dir,
            recognition_dir=layout.recognition_dir,
            student_id=student_id_from_pdf_stem(layout.name),
            crops_dir=layout.crops_dir,
        )

    def process_pdf(
        self, pdf_name: str, reporter: JobReporter, *, student_id: str | None = None
    ) -> ProcessResult:
        """Whole pipeline for one PDF with every checkpoint auto-accepted (API)."""
        config = self.config
        pdf = files.require_input_file(config.input.jawaban_dir, pdf_name, suffix=".pdf")
        layout = layout_for_pdf(config.output.root_dir, pdf)
        controller = self._process_controller(layout, reporter)
        return controller.process(
            pdf,
            pages_dir=layout.pages_dir,
            recognition_dir=layout.recognition_dir,
            questions_dir=layout.questions_dir,
            output_dir=layout.report_dir,
            dpi=config.pdf.dpi,
            student_id=student_id or student_id_from_pdf_stem(pdf.stem),
            workspace_root=layout.root,
            reset_workspace=True,
            crops_dir=layout.crops_dir,
        )

    def results(self, run_name: str) -> ResultsView:
        layout = self.run(run_name)
        try:
            report = load_exam_report(layout.root)
        except ValueError as exc:
            raise QuestionArtifactsInvalidError([str(exc)]) from exc
        grades: list[QuestionResult] = []
        for path in paired_grading_artifact_paths(layout.questions_dir):
            try:
                grade = load_question_grade(path)
            except ValueError:
                grade = None
            grades.append(QuestionResult(question_id=path.parent.name, grade=grade))
        return ResultsView(
            run=layout.name,
            report=report,
            grades=grades,
            report_files=files.existing_report_files(layout),
        )

    def question_grade(self, run_name: str, question_ref: str) -> tuple[Path, QuestionGrade]:
        layout = self.run(run_name)
        try:
            folder = parse_question_ref(question_ref)
        except ValueError:
            folder = question_ref
        path = layout.questions_dir / Path(folder).name / grading_filename()
        if not path.is_file():
            raise ArtifactNotFoundError(f"grading.json untuk {question_ref} di run {layout.name}")
        try:
            return path, load_question_grade(path)
        except ValueError as exc:
            raise QuestionArtifactsInvalidError([str(exc)]) from exc

    # --- helpers --------------------------------------------------------------

    def _standard_dir(self, topic_id: str | None = None) -> Path:
        return topic_standard_dir(
            self.config.grading.standards_root, topic_id or self._session.topic_id
        )

    def _standard_ready(self, topic_id: str) -> bool:
        return exam_schema_path(self._standard_dir(topic_id)).is_file()

    def _summary(self, layout: RunLayout) -> RunSummary:
        try:
            report = load_exam_report(layout.root)
        except ValueError:
            report = None
        return RunSummary(
            name=layout.name,
            short_name=shorten_pdf_name(Path(f"{layout.name}.pdf")).removesuffix(".pdf"),
            student_id=student_id_from_pdf_stem(layout.name),
            steps=RunSteps(
                pages=len(self._pages(layout, strict=False)),
                crops=crops_regions_present(layout.crops_dir),
                labels=question_crops_dir(layout.crops_dir).is_dir(),
                questions=len(question_artifact_paths(layout.questions_dir)),
                graded=bool(paired_grading_artifact_paths(layout.questions_dir)),
                report=report is not None,
            ),
            total_score=report.total_score if report else None,
            maximum_total=report.maximum_total if report else None,
            report_files=files.existing_report_files(layout),
        )

    @staticmethod
    def _pages(layout: RunLayout, *, strict: bool = True) -> list[Page]:
        try:
            return load_pages_from_dir(layout.pages_dir)
        except (FileNotFoundError, ValueError) as exc:
            if not strict:
                return []
            raise ArtifactNotFoundError(
                f"halaman ter-render di run {layout.name}; jalankan Propose crops dulu"
            ) from exc

    @staticmethod
    def _crop_names(layout: RunLayout, page_number: int, count: int) -> list[str]:
        page_dir = layout.crops_dir / f"page_{page_number:03d}"
        return [path.name for path in crop_paths_for(page_dir, page_number, count)]

    def _crop_controller(self, layout: RunLayout) -> CropController:
        return pipeline_factory.build_crop_controller(
            self.config, layout.recognition_dir, crops_dir=layout.crops_dir
        )

    def _label_controller(self, layout: RunLayout) -> QuestionLabelController:
        return pipeline_factory.build_question_label_controller(self.config, layout.crops_dir)

    def _label_view(
        self,
        layout: RunLayout,
        questions: list[ExamQuestion],
        report: QuestionCropsReport | None,
    ) -> LabelView:
        try:
            mapping = load_question_crops(layout.crops_dir) or {}
        except ValueError:
            mapping = {}
        numbers_by_crop = crop_to_questions(mapping)
        return LabelView(
            run=layout.name,
            rows=[
                LabelRow(crop=crop, numbers=numbers_by_crop.get(crop.name, []))
                for crop in list_crops_in_reading_order(layout.crops_dir)
            ],
            questions=questions,
            report=report,
        )

    def _process_controller(self, layout: RunLayout, reporter: JobReporter) -> ProcessController:
        return pipeline_factory.build_process_controller(
            self.config,
            recognition_dir=layout.recognition_dir,
            crops_dir=layout.crops_dir,
            standard_dir=pipeline_factory.resolve_standard_dir(
                self.config, topic_id=self._session.explicit_topic_id
            ),
            topic_id=self._session.explicit_topic_id,
            on_progress=reporter.progress,
            on_question_crops_missing=lambda crops_dir: reporter.message(
                f"Belum ada nomor soal per crop ({crops_dir.name}/question_crops); "
                "model akan menebak nomor soal."
            ),
        )


def _validation_summary(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
