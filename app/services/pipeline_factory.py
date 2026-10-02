"""Shared ProcessController wiring for CLI and API (DRY)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.config import AppConfig
from app.controllers.crop_controller import CropController
from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.ingest_kunci_controller import IngestKunciController
from app.controllers.latex_controller import LatexController
from app.controllers.process_controller import ProcessController
from app.controllers.question_label_controller import QuestionLabelController
from app.controllers.question_review_controller import QuestionReviewController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.exceptions import ExamSchemaMissingError
from app.functions.kunci_ingest import load_exam_schema
from app.functions.run_layout import (
    CROPS_SUBDIR,
    FALLBACK_RUN_NAME,
    RunLayout,
    build_run_layout,
)
from app.functions.workspace_reset import DEFAULT_PRESERVE, prepare_pipeline_workspace
from app.interfaces.latex_compiler import LatexCompiler
from app.interfaces.llm_client import LlmClient
from app.interfaces.topic_pack import TopicPack
from app.interfaces.validator import StepValidator
from app.models.recognition import RecognizeResult
from app.models.report import PromptVersions
from app.services.grading.feedback_annotator import FeedbackAnnotator
from app.services.grading.feedback_annotator import PROMPT_VERSION as GRADING_PROMPT_VERSION
from app.services.grading.latex_report import LatexReportWriter
from app.services.grading.report import JsonCsvHtmlReporter
from app.services.grading.rubric import RubricLoader
from app.services.grading.standard_comparer import StandardFinalComparer
from app.services.grading.step_grader import StepGrader
from app.services.latex.builder import LatexBuilder
from app.services.latex.pdflatex_compiler import PdfLatexCompiler, resolve_pdflatex
from app.services.math.hybrid_validator import HybridStepValidator
from app.services.math.llm_judge import PROMPT_VERSION as VALIDATION_PROMPT_VERSION
from app.services.math.llm_judge import LlmStepJudge
from app.services.math.sympy_validator import SymPyStepValidator
from app.services.pdf.renderer import PyMuPdfRenderer
from app.services.questions.extractor import QuestionExtractor
from app.services.standards.kunci_ingester import KunciIngester
from app.services.standards.standard_dir import resolve_standard_dir
from app.services.vision.factory import build_vision_recognizer
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.question_labeler import OllamaQuestionLabeler
from app.services.vision.recognizer import PROMPT_VERSION as RECOGNITION_PROMPT_VERSION
from app.topics.runtime import set_active_pack


def resolve_topic_pack(
    config: AppConfig,
    *,
    topic_id: str | None = None,
    standard_dir: Path | None = None,
    prefer_schema: bool = True,
) -> TopicPack:
    """Resolve pack from CLI topic, exam_schema, then config.grading.topic_id."""
    from app.topics.registry import get_pack

    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    if topic_id is not None and str(topic_id).strip():
        return get_pack(topic_id)
    if prefer_schema:
        schema = load_exam_schema(standard)
        if schema is not None and (schema.topic_id or "").strip():
            return get_pack(schema.topic_id)
    return get_pack(config.grading.topic_id)


def build_ollama_client(config: AppConfig) -> LlmClient:
    return OllamaClient(
        base_url=config.ollama.base_url,
        timeout_seconds=config.ollama.timeout_seconds,
        max_retries=config.ollama.max_retries,
    )


def default_run_layout(config: AppConfig) -> RunLayout:
    """Layout used only when a caller wires controllers without a PDF/run."""
    return build_run_layout(config.output.root_dir, FALLBACK_RUN_NAME)


def prepare_run_workspace(
    layout: RunLayout,
    *,
    pages_dir: Path | None = None,
    recognition_dir: Path | None = None,
    questions_dir: Path | None = None,
    preserve_crops: bool = False,
) -> list[str]:
    """Clear only ``layout.root`` (plus overridden dirs outside it) for a new run.

    ``preserve_crops`` keeps ``crops/`` (regions JSON + question_crops) so
    ``--use-existing-crops`` can reuse them.
    """
    return prepare_pipeline_workspace(
        layout.root,
        pages_dir=pages_dir if pages_dir is not None else layout.pages_dir,
        recognition_dir=(
            recognition_dir if recognition_dir is not None else layout.recognition_dir
        ),
        questions_dir=(
            questions_dir if questions_dir is not None else layout.questions_dir
        ),
        crops_dir=layout.crops_dir,
        preserve=DEFAULT_PRESERVE | {CROPS_SUBDIR} if preserve_crops else DEFAULT_PRESERVE,
        keep_crops=preserve_crops,
    )


def build_validator(config: AppConfig, pack: TopicPack | None = None) -> StepValidator:
    """SymPy validator (+ LLM fallback) using the pack's role → check mapping."""
    step_checks = pack.step_checks if pack is not None else None
    validator: StepValidator = SymPyStepValidator(step_checks=step_checks)
    if config.ollama.reasoning_model.strip():
        validator = HybridStepValidator(
            sympy_validator=validator,
            llm_judge=LlmStepJudge(
                client=build_ollama_client(config),
                model=config.ollama.reasoning_model,
            ),
            step_checks=step_checks,
        )
    return validator


def build_validate_controller(
    config: AppConfig,
    standard_dir: Path | None = None,
    *,
    topic_id: str | None = None,
) -> ValidateController:
    """Standalone ``validate`` must normalize with the same pack as ``process``."""
    pack = resolve_topic_pack(config, topic_id=topic_id, standard_dir=standard_dir)
    set_active_pack(pack)
    return ValidateController(build_validator(config, pack))


def build_grade_controller(
    config: AppConfig,
    standard_dir: Path | None = None,
    *,
    topic_id: str | None = None,
) -> GradeController:
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    pack = resolve_topic_pack(config, topic_id=topic_id, standard_dir=standard)
    set_active_pack(pack)
    annotator = None
    if config.ollama.reasoning_model.strip():
        annotator = FeedbackAnnotator(
            client=build_ollama_client(config),
            model=config.ollama.reasoning_model,
        )
    grader = StepGrader(
        rubric_loader=RubricLoader(standard),
        feedback_annotator=annotator,
        standard_comparer=StandardFinalComparer(
            standard,
            exam_schema=load_exam_schema(standard),
        ),
    )
    return GradeController(grader=grader, standard_dir=standard)


def build_report_controller(
    config: AppConfig,
    standard_dir: Path | None = None,
    *,
    topic_id: str | None = None,
) -> ReportController:
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    return ReportController(
        reporter=JsonCsvHtmlReporter(),
        standard_dir=standard,
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
        prompt_versions=current_prompt_versions(),
        latex_reporter=LatexReportWriter(),
        pdf_compiler=build_pdf_compiler(config),
    )


def build_pdf_compiler(config: AppConfig) -> LatexCompiler | None:
    """``report.tex`` → ``report.pdf`` after grading; ``None`` when disabled in config."""
    pdf = config.report.pdf
    if not pdf.enabled:
        return None
    return PdfLatexCompiler(
        resolve_pdflatex(pdf.pdflatex_path),
        passes=pdf.passes,
        timeout_seconds=pdf.timeout_seconds,
    )


def current_prompt_versions() -> PromptVersions:
    return PromptVersions(
        recognition=RECOGNITION_PROMPT_VERSION,
        validation=VALIDATION_PROMPT_VERSION,
        grading=GRADING_PROMPT_VERSION,
    )


def _recognition_dir_or_default(config: AppConfig, recognition_dir: Path | None) -> Path:
    if recognition_dir is not None:
        return Path(recognition_dir)
    return default_run_layout(config).recognition_dir


def _activate_pack(
    config: AppConfig, *, topic_id: str | None, standard_dir: Path | None
) -> Path:
    """Resolve the topic standards folder and make its pack active; return the folder."""
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    set_active_pack(resolve_topic_pack(config, topic_id=topic_id, standard_dir=standard))
    return standard


def build_recognize_controller(
    config: AppConfig,
    recognition_dir: Path | None = None,
    *,
    crops_dir: Path | None = None,
    standard_dir: Path | None = None,
    topic_id: str | None = None,
) -> RecognizeController:
    recognition = _recognition_dir_or_default(config, recognition_dir)
    standard = _activate_pack(config, topic_id=topic_id, standard_dir=standard_dir)
    return RecognizeController(
        renderer=PyMuPdfRenderer(),
        recognizer=build_vision_recognizer(
            config, recognition, crops_dir=crops_dir, standard_dir=standard
        ),
    )


def build_render_controller() -> RenderController:
    return RenderController(PyMuPdfRenderer())


def build_extract_controller(
    config: AppConfig,
    standard_dir: Path | None = None,
    *,
    topic_id: str | None = None,
    recognize_runner: Callable[[], RecognizeResult] | None = None,
) -> ExtractController:
    standard = _activate_pack(config, topic_id=topic_id, standard_dir=standard_dir)
    return ExtractController(
        extractor=QuestionExtractor(exam_schema=load_exam_schema(standard)),
        recognize_runner=recognize_runner,
    )


def build_latex_controller() -> LatexController:
    return LatexController(LatexBuilder())


def build_crop_controller(
    config: AppConfig,
    recognition_dir: Path | None = None,
    *,
    crops_dir: Path | None = None,
    standard_dir: Path | None = None,
    topic_id: str | None = None,
) -> CropController:
    recognition = _recognition_dir_or_default(config, recognition_dir)
    recognizer = build_vision_recognizer(
        config,
        recognition,
        crops_dir=crops_dir,
        standard_dir=resolve_standard_dir(
            config, topic_id=topic_id, standard_dir=standard_dir
        ),
    )
    return CropController(
        renderer=PyMuPdfRenderer(),
        workspace=recognizer,
    )


def build_ingest_kunci_controller(
    config: AppConfig,
    standard_dir: Path | None = None,
    *,
    topic_id: str | None = None,
) -> IngestKunciController:
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    # Fresh ingest ignores stale schema.topic_id; uses CLI/config topic.
    pack = resolve_topic_pack(
        config,
        topic_id=topic_id,
        standard_dir=standard,
        prefer_schema=False,
    )
    set_active_pack(pack)
    return IngestKunciController(KunciIngester(standard, topic_pack=pack))


def build_process_controller(
    config: AppConfig,
    *,
    recognition_dir: Path | None = None,
    crops_dir: Path | None = None,
    standard_dir: Path | None = None,
    topic_id: str | None = None,
    on_progress=None,
    on_question_crops_missing=None,
) -> ProcessController:
    """Wire MVC controllers for end-to-end ``process`` (CLI and API)."""
    recognition = _recognition_dir_or_default(config, recognition_dir)
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    pack = resolve_topic_pack(config, topic_id=topic_id, standard_dir=standard)
    set_active_pack(pack)
    schema = load_exam_schema(standard)
    recognizer = build_vision_recognizer(
        config, recognition, crops_dir=crops_dir, standard_dir=standard
    )
    renderer = PyMuPdfRenderer()
    return ProcessController(
        render_controller=RenderController(renderer),
        recognize_controller=RecognizeController(
            renderer=renderer, recognizer=recognizer
        ),
        crop_controller=CropController(renderer=renderer, workspace=recognizer),
        extract_controller=ExtractController(
            extractor=QuestionExtractor(exam_schema=schema)
        ),
        latex_controller=build_latex_controller(),
        validate_controller=ValidateController(build_validator(config, pack)),
        grade_controller=build_grade_controller(
            config, standard, topic_id=topic_id
        ),
        report_controller=build_report_controller(config, standard),
        on_progress=on_progress,
        question_numbers=[q.number for q in schema.questions] if schema else [],
        on_question_crops_missing=on_question_crops_missing,
        question_review=build_question_review_controller(config),
    )


def build_question_review_controller(config: AppConfig) -> QuestionReviewController:
    return QuestionReviewController(min_confidence=config.recognition.review_min_confidence)


def build_question_label_controller(
    config: AppConfig,
    crops_dir: Path,
    standard_dir: Path | None = None,
    *,
    topic_id: str | None = None,
) -> QuestionLabelController:
    """Question-number labeling needs the kunci schema; vision labeler is optional."""
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    schema = load_exam_schema(standard)
    if schema is None or not schema.questions:
        raise ExamSchemaMissingError(standard)
    labeler = None
    if config.ollama.vision_model.strip():
        labeler = OllamaQuestionLabeler(
            client=build_ollama_client(config),
            model=config.ollama.vision_model,
            exam_schema=schema,
        )
    return QuestionLabelController(
        crops_dir=crops_dir, exam_schema=schema, labeler=labeler
    )
