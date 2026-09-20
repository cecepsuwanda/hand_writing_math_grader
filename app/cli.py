"""CLI bootstrap: parse args, wire dependencies, print results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import DEFAULT_CONFIG_PATH, AppConfig, load_config
from app.controllers.extract_controller import ExtractController
from app.controllers.grade_controller import GradeController
from app.controllers.latex_controller import LatexController
from app.controllers.process_controller import ProcessController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.render_controller import RenderController
from app.controllers.report_controller import ReportController
from app.controllers.validate_controller import ValidateController
from app.exceptions import (
    InvalidPdfSelectionError,
    MathGraderError,
    NoJawabanPdfError,
    OllamaModelNotConfiguredError,
    PdfNotFoundError,
)
from app.functions.paths import list_jawaban_pdfs, parse_pdf_choice, resolve_jawaban_pdf
from app.services.grading.feedback_annotator import FeedbackAnnotator
from app.services.grading.report import JsonCsvHtmlReporter
from app.services.grading.rubric import RubricLoader
from app.services.grading.step_grader import StepGrader
from app.services.latex.builder import LatexBuilder
from app.services.math.hybrid_validator import HybridStepValidator
from app.services.math.llm_judge import LlmStepJudge
from app.services.math.sympy_validator import SymPyStepValidator
from app.services.pdf.renderer import PyMuPdfRenderer
from app.services.questions.extractor import QuestionExtractor
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.recognizer import OllamaVisionRecognizer
from app.views.error_view import print_error
from app.views.progress_view import (
    print_models,
    print_process_summary,
    print_progress,
)
from app.views.result_view import (
    print_extract_result,
    print_grade_result,
    print_latex_result,
    print_recognize_result,
    print_render_result,
    print_report_result,
    print_validate_result,
)
from app.views.selection_view import (
    print_jawaban_menu,
    print_output_cleared,
    print_selected_pdf,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Handwritten math grader (CLI)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml (default: app/config/config.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render a PDF to per-page PNG images")
    render_parser.add_argument(
        "pdf",
        type=Path,
        help="Student answer PDF (searched under data/input/jawaban if needed)",
    )
    render_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for page PNGs (default: config pdf.output_dir)",
    )
    render_parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Render DPI (default: config pdf.dpi)",
    )

    recognize_parser = subparsers.add_parser(
        "recognize",
        help="Render a PDF and run Ollama vision recognition",
    )
    recognize_parser.add_argument(
        "pdf",
        type=Path,
        help="Student answer PDF (searched under data/input/jawaban if needed)",
    )
    recognize_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for recognition JSON (default: config recognition.output_dir)",
    )
    recognize_parser.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="Directory for page PNGs (default: config pdf.output_dir)",
    )
    recognize_parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Render DPI (default: config pdf.dpi)",
    )

    extract_parser = subparsers.add_parser(
        "extract",
        help="Merge recognition JSON into per-question artifacts",
    )
    extract_parser.add_argument(
        "pdf",
        type=Path,
        help="Student answer PDF (searched under data/input/jawaban if needed)",
    )
    extract_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for question artifacts (default: config questions.output_dir)",
    )
    extract_parser.add_argument(
        "--recognition-dir",
        type=Path,
        default=None,
        help="Directory with page_*_recognition.json (default: config recognition.output_dir)",
    )
    extract_parser.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="Directory for page PNGs if recognition must run first",
    )
    extract_parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Render DPI if recognition must run first",
    )
    extract_parser.add_argument(
        "--force-recognize",
        action="store_true",
        help="Always run recognition before extract, even if JSON exists",
    )

    latex_parser = subparsers.add_parser(
        "latex",
        help="Build student.tex from extracted question.json files",
    )
    latex_parser.add_argument(
        "--questions-dir",
        type=Path,
        default=None,
        help="Directory with question_*/question.json (default: config questions.output_dir)",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate student steps with SymPy (writes validation.json)",
    )
    validate_parser.add_argument(
        "--questions-dir",
        type=Path,
        default=None,
        help="Directory with question_*/question.json (default: config questions.output_dir)",
    )

    grade_parser = subparsers.add_parser(
        "grade",
        help="Grade validated questions against a rubric standard",
    )
    grade_parser.add_argument(
        "--questions-dir",
        type=Path,
        default=None,
        help="Directory with question_*/ (default: config questions.output_dir)",
    )
    grade_parser.add_argument(
        "--standard",
        type=Path,
        default=None,
        help="Standards directory (default: config grading.standard_dir)",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Build JSON/CSV/HTML report from grading.json artifacts",
    )
    report_parser.add_argument(
        "--questions-dir",
        type=Path,
        default=None,
        help="Directory with question_*/grading.json (default: config questions.output_dir)",
    )
    report_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for report files (default: config report.output_dir)",
    )
    report_parser.add_argument(
        "--student-id",
        type=str,
        default="student_001",
        help="Student identifier for summary CSV (default: student_001)",
    )
    report_parser.add_argument(
        "--standard",
        type=Path,
        default=None,
        help="Standards directory recorded in metadata (default: config grading.standard_dir)",
    )

    process_parser = subparsers.add_parser(
        "process",
        help="Run full pipeline: render → recognize → extract → latex → validate → grade → report",
    )
    process_parser.add_argument(
        "pdf",
        nargs="?",
        default=None,
        type=Path,
        help=(
            "Student answer PDF under data/input/jawaban "
            "(omit to choose interactively from that folder)"
        ),
    )
    process_parser.add_argument(
        "--standard",
        type=Path,
        default=None,
        help="Standards directory (default: config grading.standard_dir)",
    )
    process_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report output directory (default: config report.output_dir)",
    )
    process_parser.add_argument(
        "--student-id",
        type=str,
        default="student_001",
        help="Student identifier (default: student_001)",
    )
    process_parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Render DPI (default: config pdf.dpi)",
    )
    process_parser.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="Directory for page PNGs (default: config pdf.output_dir)",
    )
    process_parser.add_argument(
        "--recognition-dir",
        type=Path,
        default=None,
        help="Directory for recognition JSON (default: config recognition.output_dir)",
    )
    process_parser.add_argument(
        "--questions-dir",
        type=Path,
        default=None,
        help="Directory for question artifacts (default: config questions.output_dir)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            return _run_render(args)
        if args.command == "recognize":
            return _run_recognize(args)
        if args.command == "extract":
            return _run_extract(args)
        if args.command == "latex":
            return _run_latex(args)
        if args.command == "validate":
            return _run_validate(args)
        if args.command == "grade":
            return _run_grade(args)
        if args.command == "report":
            return _run_report(args)
        if args.command == "process":
            return _run_process(args)
        parser.error(f"unknown command: {args.command}")
    except MathGraderError as exc:
        print_error(exc)
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI boundary maps unexpected → exit 2
        print_error(exc)
        return 2
    return 1


def _resolve_pdf(args: argparse.Namespace, config: AppConfig) -> Path:
    if getattr(args, "pdf", None) is None:
        return _select_pdf_interactive(config.input.jawaban_dir)
    resolved = resolve_jawaban_pdf(args.pdf, config.input.jawaban_dir)
    if not resolved.is_file():
        raise PdfNotFoundError(resolved)
    return resolved


def _select_pdf_interactive(jawaban_dir: Path) -> Path:
    pdfs = list_jawaban_pdfs(jawaban_dir)
    if not pdfs:
        raise NoJawabanPdfError(jawaban_dir)
    print_jawaban_menu(pdfs, jawaban_dir)
    while True:
        try:
            raw = input("Pilihan: ")
        except EOFError as exc:
            raise InvalidPdfSelectionError("no input received") from exc
        try:
            selected = parse_pdf_choice(pdfs, raw)
        except ValueError as exc:
            print_error(InvalidPdfSelectionError(str(exc)))
            continue
        print_selected_pdf(selected)
        return selected


def _run_render(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pdf_path = _resolve_pdf(args, config)
    output_dir = args.output if args.output is not None else config.pdf.output_dir
    dpi = args.dpi if args.dpi is not None else config.pdf.dpi
    controller = RenderController(PyMuPdfRenderer())
    result = controller.render(pdf_path, output_dir, dpi)
    print_render_result(result)
    return 0


def _run_recognize(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if not config.ollama.vision_model.strip():
        raise OllamaModelNotConfiguredError()

    pdf_path = _resolve_pdf(args, config)
    pages_dir = args.pages_dir if args.pages_dir is not None else config.pdf.output_dir
    recognition_dir = (
        args.output if args.output is not None else config.recognition.output_dir
    )
    dpi = args.dpi if args.dpi is not None else config.pdf.dpi

    result = _build_recognize_controller(config, recognition_dir).recognize(
        pdf_path=pdf_path,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        dpi=dpi,
    )
    print_recognize_result(result)
    return 0


def _run_extract(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pdf_path = _resolve_pdf(args, config)
    recognition_dir = (
        args.recognition_dir
        if args.recognition_dir is not None
        else config.recognition.output_dir
    )
    output_dir = args.output if args.output is not None else config.questions.output_dir
    pages_dir = args.pages_dir if args.pages_dir is not None else config.pdf.output_dir
    dpi = args.dpi if args.dpi is not None else config.pdf.dpi

    def recognize_runner():
        if not config.ollama.vision_model.strip():
            raise OllamaModelNotConfiguredError()
        return _build_recognize_controller(config, recognition_dir).recognize(
            pdf_path=pdf_path,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            dpi=dpi,
        )

    controller = ExtractController(
        extractor=QuestionExtractor(),
        recognize_runner=recognize_runner,
    )
    result = controller.extract(
        recognition_dir=recognition_dir,
        output_dir=output_dir,
        force_recognize=bool(args.force_recognize),
    )
    print_extract_result(result)
    return 0


def _run_latex(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = (
        args.questions_dir
        if args.questions_dir is not None
        else config.questions.output_dir
    )
    controller = LatexController(LatexBuilder())
    result = controller.build(questions_dir)
    print_latex_result(result)
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = (
        args.questions_dir
        if args.questions_dir is not None
        else config.questions.output_dir
    )
    controller = ValidateController(_build_validator(config))
    result = controller.validate(questions_dir)
    print_validate_result(result)
    return 0


def _run_grade(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = (
        args.questions_dir
        if args.questions_dir is not None
        else config.questions.output_dir
    )
    standard_dir = (
        args.standard if args.standard is not None else config.grading.standard_dir
    )
    controller = _build_grade_controller(config, standard_dir)
    result = controller.grade(questions_dir)
    print_grade_result(result)
    return 0


def _run_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = (
        args.questions_dir
        if args.questions_dir is not None
        else config.questions.output_dir
    )
    output_dir = args.output if args.output is not None else config.report.output_dir
    standard_dir = (
        args.standard if args.standard is not None else config.grading.standard_dir
    )
    controller = _build_report_controller(config, standard_dir)
    result = controller.report(
        questions_dir,
        output_dir,
        student_id=args.student_id,
    )
    print_report_result(result)
    return 0


def _run_process(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if not config.ollama.vision_model.strip():
        raise OllamaModelNotConfiguredError()

    pdf_path = _resolve_pdf(args, config)
    pages_dir = args.pages_dir if args.pages_dir is not None else config.pdf.output_dir
    recognition_dir = (
        args.recognition_dir
        if args.recognition_dir is not None
        else config.recognition.output_dir
    )
    questions_dir = (
        args.questions_dir
        if args.questions_dir is not None
        else config.questions.output_dir
    )
    output_dir = args.output if args.output is not None else config.report.output_dir
    standard_dir = (
        args.standard if args.standard is not None else config.grading.standard_dir
    )
    dpi = args.dpi if args.dpi is not None else config.pdf.dpi

    print_models(
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )

    controller = ProcessController(
        render_controller=RenderController(PyMuPdfRenderer()),
        recognize_controller=_build_recognize_controller(config, recognition_dir),
        extract_controller=ExtractController(extractor=QuestionExtractor()),
        latex_controller=LatexController(LatexBuilder()),
        validate_controller=ValidateController(_build_validator(config)),
        grade_controller=_build_grade_controller(config, standard_dir),
        report_controller=_build_report_controller(config, standard_dir),
        on_progress=print_progress,
        on_output_cleared=print_output_cleared,
    )
    result = controller.process(
        pdf_path,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        output_dir=output_dir,
        dpi=dpi,
        student_id=args.student_id,
        workspace_root=config.report.output_dir,
    )
    print_process_summary(result)
    return 0


def _build_recognize_controller(
    config: AppConfig, recognition_dir: Path
) -> RecognizeController:
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
    return RecognizeController(
        renderer=PyMuPdfRenderer(),
        recognizer=recognizer,
    )


def _build_validator(config: AppConfig):
    validator = SymPyStepValidator()
    if config.ollama.reasoning_model.strip():
        client = OllamaClient(
            base_url=config.ollama.base_url,
            timeout_seconds=config.ollama.timeout_seconds,
            max_retries=config.ollama.max_retries,
        )
        validator = HybridStepValidator(
            sympy_validator=validator,
            llm_judge=LlmStepJudge(
                client=client,
                model=config.ollama.reasoning_model,
            ),
        )
    return validator


def _build_grade_controller(config: AppConfig, standard_dir: Path) -> GradeController:
    annotator = None
    if config.ollama.reasoning_model.strip():
        client = OllamaClient(
            base_url=config.ollama.base_url,
            timeout_seconds=config.ollama.timeout_seconds,
            max_retries=config.ollama.max_retries,
        )
        annotator = FeedbackAnnotator(
            client=client,
            model=config.ollama.reasoning_model,
        )
    grader = StepGrader(
        rubric_loader=RubricLoader(standard_dir),
        feedback_annotator=annotator,
    )
    return GradeController(grader=grader, standard_dir=standard_dir)


def _build_report_controller(
    config: AppConfig, standard_dir: Path
) -> ReportController:
    return ReportController(
        reporter=JsonCsvHtmlReporter(),
        standard_dir=standard_dir,
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )


if __name__ == "__main__":
    sys.exit(main())
