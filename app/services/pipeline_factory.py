"""Shared ProcessController wiring for CLI and API (DRY)."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.latex_controller import LatexController
from app.controllers.process_controller import ProcessController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.functions.kunci_ingest import load_exam_schema
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
from app.services.vision.factory import build_vision_recognizer
from app.services.vision.ollama_client import OllamaClient


def build_ollama_client(config: AppConfig) -> OllamaClient:
    return OllamaClient(
        base_url=config.ollama.base_url,
        timeout_seconds=config.ollama.timeout_seconds,
        max_retries=config.ollama.max_retries,
    )


def build_validator(config: AppConfig) -> SymPyStepValidator | HybridStepValidator:
    validator: SymPyStepValidator | HybridStepValidator = SymPyStepValidator()
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


def build_process_controller(
    config: AppConfig,
    *,
    recognition_dir: Path | None = None,
    standard_dir: Path | None = None,
    on_progress=None,
    on_output_cleared=None,
) -> ProcessController:
    """Wire MVC controllers for end-to-end ``process`` (CLI and API)."""
    recognition = (
        Path(recognition_dir)
        if recognition_dir is not None
        else config.recognition.output_dir
    )
    standard = Path(standard_dir) if standard_dir is not None else config.grading.standard_dir
    return ProcessController(
        render_controller=RenderController(PyMuPdfRenderer()),
        recognize_controller=build_recognize_controller(config, recognition),
        extract_controller=ExtractController(
            extractor=QuestionExtractor(
                exam_schema=load_exam_schema(standard),
            )
        ),
        latex_controller=LatexController(LatexBuilder()),
        validate_controller=ValidateController(build_validator(config)),
        grade_controller=build_grade_controller(config, standard),
        report_controller=build_report_controller(config, standard),
        on_progress=on_progress,
        on_output_cleared=on_output_cleared,
    )
