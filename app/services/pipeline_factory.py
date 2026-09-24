"""Shared ProcessController wiring for CLI and API (DRY)."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.controllers.crop_controller import CropController
from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.ingest_kunci_controller import IngestKunciController
from app.controllers.latex_controller import LatexController
from app.controllers.process_controller import ProcessController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.functions.kunci_ingest import load_exam_schema
from app.interfaces.llm_client import LlmClient
from app.interfaces.validator import StepValidator
from app.services.grading.feedback_annotator import FeedbackAnnotator
from app.services.grading.report import JsonCsvHtmlReporter
from app.services.grading.rubric import RubricLoader
from app.services.grading.standard_comparer import StandardFinalComparer
from app.services.grading.step_grader import StepGrader
from app.services.latex.builder import LatexBuilder
from app.services.math.hybrid_validator import HybridStepValidator
from app.services.math.llm_judge import LlmStepJudge
from app.services.math.sympy_validator import SymPyStepValidator
from app.services.pdf.renderer import PyMuPdfRenderer
from app.services.questions.extractor import QuestionExtractor
from app.services.standards.kunci_ingester import KunciIngester
from app.services.vision.factory import build_vision_recognizer
from app.services.vision.ollama_client import OllamaClient
from app.services.workspace.cleaner import prepare_pipeline_workspace


def build_ollama_client(config: AppConfig) -> LlmClient:
    return OllamaClient(
        base_url=config.ollama.base_url,
        timeout_seconds=config.ollama.timeout_seconds,
        max_retries=config.ollama.max_retries,
    )


def prepare_run_workspace(
    config: AppConfig,
    *,
    workspace_root: Path | None = None,
    pages_dir: Path | None = None,
    recognition_dir: Path | None = None,
    questions_dir: Path | None = None,
    crops_dir: Path | None = None,
) -> list[str]:
    """Clear pipeline output dirs for a new crop/process run (composition helper)."""
    return prepare_pipeline_workspace(
        workspace_root if workspace_root is not None else config.report.output_dir,
        pages_dir=pages_dir if pages_dir is not None else config.pdf.output_dir,
        recognition_dir=(
            recognition_dir
            if recognition_dir is not None
            else config.recognition.output_dir
        ),
        questions_dir=(
            questions_dir if questions_dir is not None else config.questions.output_dir
        ),
        crops_dir=crops_dir if crops_dir is not None else config.recognition.crops_dir,
    )


def build_validator(config: AppConfig) -> StepValidator:
    validator: StepValidator = SymPyStepValidator()
    if config.ollama.reasoning_model.strip():
        validator = HybridStepValidator(
            sympy_validator=SymPyStepValidator(),
            llm_judge=LlmStepJudge(
                client=build_ollama_client(config),
                model=config.ollama.reasoning_model,
            ),
        )
    return validator


def build_grade_controller(
    config: AppConfig, standard_dir: Path | None = None
) -> GradeController:
    standard = Path(standard_dir) if standard_dir is not None else config.grading.standard_dir
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
    config: AppConfig, standard_dir: Path | None = None
) -> ReportController:
    standard = Path(standard_dir) if standard_dir is not None else config.grading.standard_dir
    return ReportController(
        reporter=JsonCsvHtmlReporter(),
        standard_dir=standard,
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )


def build_recognize_controller(
    config: AppConfig, recognition_dir: Path | None = None
) -> RecognizeController:
    recognition = (
        Path(recognition_dir)
        if recognition_dir is not None
        else config.recognition.output_dir
    )
    return RecognizeController(
        renderer=PyMuPdfRenderer(),
        recognizer=build_vision_recognizer(config, recognition),
    )


def build_crop_controller(
    config: AppConfig, recognition_dir: Path | None = None
) -> CropController:
    recognition = (
        Path(recognition_dir)
        if recognition_dir is not None
        else config.recognition.output_dir
    )
    recognizer = build_vision_recognizer(config, recognition)
    return CropController(
        renderer=PyMuPdfRenderer(),
        recognizer=recognizer,
    )


def build_ingest_kunci_controller(
    config: AppConfig, standard_dir: Path | None = None
) -> IngestKunciController:
    standard = Path(standard_dir) if standard_dir is not None else config.grading.standard_dir
    return IngestKunciController(KunciIngester(standard))


def build_process_controller(
    config: AppConfig,
    *,
    recognition_dir: Path | None = None,
    standard_dir: Path | None = None,
    on_progress=None,
) -> ProcessController:
    """Wire MVC controllers for end-to-end ``process`` (CLI and API)."""
    recognition = (
        Path(recognition_dir)
        if recognition_dir is not None
        else config.recognition.output_dir
    )
    standard = Path(standard_dir) if standard_dir is not None else config.grading.standard_dir
    schema = load_exam_schema(standard)
    recognizer = build_vision_recognizer(config, recognition, exam_schema=schema)
    renderer = PyMuPdfRenderer()
    return ProcessController(
        render_controller=RenderController(renderer),
        recognize_controller=RecognizeController(
            renderer=renderer, recognizer=recognizer
        ),
        crop_controller=CropController(renderer=renderer, recognizer=recognizer),
        extract_controller=ExtractController(
            extractor=QuestionExtractor(exam_schema=schema)
        ),
        latex_controller=LatexController(LatexBuilder()),
        validate_controller=ValidateController(build_validator(config)),
        grade_controller=build_grade_controller(config, standard),
        report_controller=build_report_controller(config, standard),
        on_progress=on_progress,
    )
