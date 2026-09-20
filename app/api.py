"""Thin FastAPI adapter over existing MVC controllers (pasca-MVP).

CLI remains the required entry point. This module does not own grading logic.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import AppConfig, load_config
from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.latex_controller import LatexController
from app.controllers.process_controller import ProcessController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.functions.paths import resolve_jawaban_pdf
from app.functions.question_names import grading_filename, question_dir_name
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
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.recognizer import OllamaVisionRecognizer

try:
    from fastapi import FastAPI, HTTPException
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fastapi is required for the API adapter; pip install fastapi uvicorn"
    ) from exc

ProcessFactory = Callable[[AppConfig], ProcessController]

app = FastAPI(
    title="Handwriting Math Grader API",
    description="Thin HTTP adapter; engine logic stays in CLI controllers/services.",
)

_process_factory: ProcessFactory | None = None


def configure_process_factory(factory: ProcessFactory | None) -> None:
    """Override ProcessController builder (tests)."""
    global _process_factory
    _process_factory = factory


class ProcessRequest(BaseModel):
    pdf: str = Field(description="PDF path or name under jawaban_dir")
    student_id: str = "student_001"


class HealthResponse(BaseModel):
    status: str = "ok"


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/process")
def api_process(body: ProcessRequest) -> dict[str, Any]:
    config = load_config()
    try:
        pdf_path = resolve_jawaban_pdf(Path(body.pdf), config.input.jawaban_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF not found: {pdf_path}")

    factory = _process_factory or build_process_controller
    controller = factory(config)
    result = controller.process(
        pdf_path,
        pages_dir=config.pdf.output_dir,
        recognition_dir=config.recognition.output_dir,
        questions_dir=config.questions.output_dir,
        output_dir=config.report.output_dir,
        dpi=config.pdf.dpi,
        student_id=body.student_id,
        workspace_root=config.report.output_dir,
        reset_workspace=True,
    )
    return {
        "student_id": result.student_id,
        "total_score": result.total_score,
        "maximum_total": result.maximum_total,
        "overall_status": result.overall_status.value,
        "questions": [q.model_dump(mode="json") for q in result.questions],
        "output_dir": str(result.output_dir),
        "questions_dir": str(result.questions_dir),
        "report_json_path": (
            str(result.report_json_path) if result.report_json_path else None
        ),
    }


@app.get("/api/results/{question_id}")
def api_results(question_id: str) -> dict[str, Any]:
    config = load_config()
    qdir = config.questions.output_dir / question_id
    if not qdir.is_dir():
        # also accept bare numbers → question_NNN
        try:
            number = int(question_id.replace("question_", ""))
            qdir = config.questions.output_dir / question_dir_name(number)
        except ValueError:
            pass
    grading_path = qdir / grading_filename()
    if not grading_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"grading artifact not found for {question_id}",
        )
    return {
        "question_id": qdir.name,
        "grading_path": str(grading_path),
        "grading": grading_path.read_text(encoding="utf-8"),
    }


def build_process_controller(config: AppConfig) -> ProcessController:
    recognition_dir = config.recognition.output_dir
    standard_dir = config.grading.standard_dir
    client = OllamaClient(
        base_url=config.ollama.base_url,
        timeout_seconds=config.ollama.timeout_seconds,
        max_retries=config.ollama.max_retries,
    )
    recognizer = OllamaVisionRecognizer(
        client=client,
        model=config.ollama.vision_model,
        output_dir=recognition_dir,
    )
    validator: object = SymPyStepValidator()
    if config.ollama.reasoning_model.strip():
        judge_client = OllamaClient(
            base_url=config.ollama.base_url,
            timeout_seconds=config.ollama.timeout_seconds,
            max_retries=config.ollama.max_retries,
        )
        validator = HybridStepValidator(
            sympy_validator=SymPyStepValidator(),
            llm_judge=LlmStepJudge(
                client=judge_client,
                model=config.ollama.reasoning_model,
            ),
        )
    return ProcessController(
        render_controller=RenderController(PyMuPdfRenderer()),
        recognize_controller=RecognizeController(
            renderer=PyMuPdfRenderer(),
            recognizer=recognizer,
        ),
        extract_controller=ExtractController(extractor=QuestionExtractor()),
        latex_controller=LatexController(LatexBuilder()),
        validate_controller=ValidateController(validator),  # type: ignore[arg-type]
        grade_controller=GradeController(
            grader=StepGrader(
                RubricLoader(standard_dir),
                feedback_annotator=FeedbackAnnotator(),
                standard_comparer=StandardFinalComparer(standard_dir),
            ),
            standard_dir=standard_dir,
        ),
        report_controller=ReportController(
            reporter=JsonCsvHtmlReporter(),
            standard_dir=standard_dir,
            vision_model=config.ollama.vision_model,
            reasoning_model=config.ollama.reasoning_model,
        ),
    )


def main() -> None:
    import uvicorn

    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
