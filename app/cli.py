"""CLI bootstrap: parse args, wire dependencies, print results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import DEFAULT_CONFIG_PATH, AppConfig, load_config
from app.controllers.extract_controller import ExtractController
from app.controllers.ingest_kunci_controller import IngestKunciController
from app.controllers.latex_controller import LatexController
from app.controllers.render_controller import RenderController
from app.controllers.validate_controller import ValidateController
from app.exceptions import (
    InvalidKunciSelectionError,
    InvalidMenuSelectionError,
    InvalidPdfSelectionError,
    MathGraderError,
    NoJawabanPdfError,
    NoKunciTexError,
    OllamaModelNotConfiguredError,
    PdfNotFoundError,
)
from app.functions.kunci_ingest import load_exam_schema
from app.functions.paths import (
    list_jawaban_pdfs,
    list_kunci_tex,
    parse_kunci_choice,
    parse_main_menu_choice,
    parse_pdf_choice,
    resolve_jawaban_pdf,
)
from app.services.latex.builder import LatexBuilder
from app.services.pdf.renderer import PyMuPdfRenderer
from app.services.pipeline_factory import (
    build_crop_controller,
    build_grade_controller,
    build_process_controller,
    build_recognize_controller,
    build_report_controller,
    build_validator,
)
from app.services.questions.extractor import QuestionExtractor
from app.services.workspace.cleaner import prepare_pipeline_workspace
from app.views.error_view import print_error
from app.views.exit_view import (
    mark_interactive_session_done,
    prompt_continue_or_exit,
    reset_interactive_session_flag,
    wait_for_exit,
)
from app.views.progress_view import (
    print_models,
    print_process_summary,
    print_progress,
)
from app.views.result_view import (
    print_extract_result,
    print_grade_result,
    print_ingest_kunci_result,
    print_latex_result,
    print_recognize_result,
    print_render_result,
    print_report_result,
    print_validate_result,
)
from app.views.selection_view import (
    print_jawaban_menu,
    print_kunci_menu,
    print_main_menu,
    print_output_cleared,
    print_selected_kunci,
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
    recognize_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive crop confirmation",
    )
    recognize_parser.add_argument(
        "--use-existing-crops",
        action="store_true",
        help="Reuse existing page_*_regions.json instead of re-running ink propose",
    )

    propose_crops_parser = subparsers.add_parser(
        "propose-crops",
        help="Ink-propose region boxes, write page_*_regions.json, crop PNGs, confirm",
    )
    propose_crops_parser.add_argument(
        "pdf",
        type=Path,
        help="Student answer PDF (searched under data/input/jawaban if needed)",
    )
    propose_crops_parser.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="Directory for page PNGs (default: config pdf.output_dir)",
    )
    propose_crops_parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Render DPI (default: config pdf.dpi)",
    )
    propose_crops_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive crop confirmation",
    )

    recrop_parser = subparsers.add_parser(
        "recrop",
        help="Re-crop PNGs from editable page_*_regions.json under crops/",
    )
    recrop_parser.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="Directory for page PNGs (default: config pdf.output_dir)",
    )
    recrop_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive crop confirmation after recrop",
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
    process_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive crop confirmation",
    )
    process_parser.add_argument(
        "--use-existing-crops",
        action="store_true",
        help="Reuse existing page_*_regions.json (skip ink re-propose)",
    )

    ingest_parser = subparsers.add_parser(
        "ingest-kunci",
        help="Ingest kunci_jawaban TeX into standards/solutions",
    )
    ingest_parser.add_argument(
        "kunci",
        type=Path,
        nargs="?",
        default=None,
        help="Kunci .tex file (default: all .tex under config input.kunci_jawaban_dir)",
    )
    ingest_parser.add_argument(
        "--standard",
        type=Path,
        default=None,
        help="Standards directory (default: config grading.standard_dir)",
    )
    ingest_parser.add_argument(
        "--kunci-dir",
        type=Path,
        default=None,
        help="Directory of kunci .tex files (default: config input.kunci_jawaban_dir)",
    )

    subparsers.add_parser(
        "menu",
        help="Interactive main menu (ingest kunci / process PDF / exit)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            return _run_render(args)
        if args.command == "propose-crops":
            return _run_propose_crops(args)
        if args.command == "recrop":
            return _run_recrop(args)
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
        if args.command == "ingest-kunci":
            return _run_ingest_kunci(args)
        if args.command == "menu":
            return _run_menu(args)
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


def _select_kunci_interactive(kunci_dir: Path) -> Path:
    tex_files = list_kunci_tex(kunci_dir)
    if not tex_files:
        raise NoKunciTexError(kunci_dir)
    print_kunci_menu(tex_files, kunci_dir)
    while True:
        try:
            raw = input("Pilihan: ")
        except EOFError as exc:
            raise InvalidKunciSelectionError("no input received") from exc
        try:
            selected = parse_kunci_choice(tex_files, raw)
        except ValueError as exc:
            print_error(InvalidKunciSelectionError(str(exc)))
            continue
        print_selected_kunci(selected)
        return selected


def _run_menu(args: argparse.Namespace) -> int:
    if not sys.stdin.isatty():
        print_error(
            MathGraderError(
                "Interactive menu requires a terminal. "
                "Use `process`, `propose-crops`, `recrop`, `ingest-kunci`, "
                "or other subcommands instead."
            )
        )
        return 1

    config = load_config(args.config)
    last_code = 0
    while True:
        print_main_menu()
        try:
            raw = input("Pilihan [1-5]: ")
        except (EOFError, KeyboardInterrupt):
            print()
            mark_interactive_session_done()
            return last_code
        try:
            choice = parse_main_menu_choice(raw)
        except ValueError as exc:
            print_error(InvalidMenuSelectionError(str(exc)))
            continue

        if choice == "exit":
            mark_interactive_session_done()
            return last_code

        try:
            if choice == "ingest":
                kunci_path = _select_kunci_interactive(config.input.kunci_jawaban_dir)
                result = IngestKunciController().ingest(
                    kunci_path=kunci_path,
                    kunci_dir=config.input.kunci_jawaban_dir,
                    standard_dir=config.grading.standard_dir,
                )
                print_ingest_kunci_result(result)
                last_code = 0
            elif choice == "propose_crops":
                pdf_path = _select_pdf_interactive(config.input.jawaban_dir)
                print_selected_pdf(pdf_path)
                last_code = _menu_propose_crops(config, args, pdf_path)
            elif choice == "recrop":
                last_code = _menu_recrop(config, args)
            elif choice == "finish":
                if not config.ollama.vision_model.strip():
                    raise OllamaModelNotConfiguredError()
                last_code = _menu_finish_from_crops(config, args)
            else:
                raise InvalidMenuSelectionError(f"unhandled choice: {choice}")
        except MathGraderError as exc:
            print_error(exc)
            last_code = 1
        except Exception as exc:  # noqa: BLE001 — CLI boundary maps unexpected → exit 2
            print_error(exc)
            last_code = 2


def _menu_propose_crops(
    config: AppConfig,
    args: argparse.Namespace,
    pdf_path: Path,
) -> int:
    pages_dir = getattr(args, "pages_dir", None) or config.pdf.output_dir
    recognition_dir = getattr(args, "recognition_dir", None) or config.recognition.output_dir
    questions_dir = getattr(args, "questions_dir", None) or config.questions.output_dir
    workspace_root = config.report.output_dir
    dpi = getattr(args, "dpi", None)
    if dpi is None:
        dpi = config.pdf.dpi

    removed = prepare_pipeline_workspace(
        workspace_root,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        crops_dir=config.recognition.crops_dir,
    )
    print_output_cleared(workspace_root, removed)

    crop = build_crop_controller(config)
    crop.propose_for_pdf(pdf_path, pages_dir, dpi)
    crop.confirm_loop(pages_dir, force_yes=False)
    print(f"Crops ready under {crop.crops_dir}")
    return 0


def _menu_recrop(config: AppConfig, args: argparse.Namespace) -> int:
    pages_dir = getattr(args, "pages_dir", None) or config.pdf.output_dir
    crop = build_crop_controller(config)
    result = crop.recrop_all(pages_dir)
    if not result.pages:
        print(f"No page_*_regions.json found under {crop.crops_dir}")
        return 1
    crop.confirm_loop(pages_dir, force_yes=False)
    print(f"Recropped {len(result.pages)} page(s) under {crop.crops_dir}")
    return 0


def _menu_finish_from_crops(config: AppConfig, args: argparse.Namespace) -> int:
    pages_dir = getattr(args, "pages_dir", None) or config.pdf.output_dir
    recognition_dir = getattr(args, "recognition_dir", None) or config.recognition.output_dir
    questions_dir = getattr(args, "questions_dir", None) or config.questions.output_dir
    output_dir = getattr(args, "output", None) or config.report.output_dir
    standard_dir = getattr(args, "standard", None) or config.grading.standard_dir
    student_id = getattr(args, "student_id", None) or "student_001"

    print_models(
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )
    controller = build_process_controller(
        config,
        recognition_dir=recognition_dir,
        standard_dir=standard_dir,
        on_progress=print_progress,
    )
    result = controller.process_from_crops(
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        output_dir=output_dir,
        student_id=student_id,
        crops_dir=config.recognition.crops_dir,
    )
    print_process_summary(result)
    return 0


def _process_one_pdf(
    config: AppConfig,
    args: argparse.Namespace,
    pdf_path: Path,
) -> int:
    """Run a single end-to-end process for ``pdf_path``; return exit code."""
    pages_dir = getattr(args, "pages_dir", None)
    if pages_dir is None:
        pages_dir = config.pdf.output_dir
    recognition_dir = getattr(args, "recognition_dir", None)
    if recognition_dir is None:
        recognition_dir = config.recognition.output_dir
    questions_dir = getattr(args, "questions_dir", None)
    if questions_dir is None:
        questions_dir = config.questions.output_dir
    output_dir = getattr(args, "output", None)
    if output_dir is None:
        output_dir = config.report.output_dir
    standard_dir = getattr(args, "standard", None)
    if standard_dir is None:
        standard_dir = config.grading.standard_dir
    dpi = getattr(args, "dpi", None)
    if dpi is None:
        dpi = config.pdf.dpi
    student_id = getattr(args, "student_id", None) or "student_001"
    workspace_root = config.report.output_dir

    removed = prepare_pipeline_workspace(
        workspace_root,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        crops_dir=config.recognition.crops_dir,
    )
    print_output_cleared(workspace_root, removed)
    print_models(
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )

    controller = build_process_controller(
        config,
        recognition_dir=recognition_dir,
        standard_dir=standard_dir,
        on_progress=print_progress,
    )
    result = controller.process(
        pdf_path,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        output_dir=output_dir,
        dpi=dpi,
        student_id=student_id,
        workspace_root=workspace_root,
        reset_workspace=False,
        crops_dir=config.recognition.crops_dir,
        force_yes=bool(getattr(args, "yes", False)),
        use_existing_crops=bool(getattr(args, "use_existing_crops", False)),
    )
    print_process_summary(result)
    return 0


def _run_render(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pdf_path = _resolve_pdf(args, config)
    output_dir = args.output if args.output is not None else config.pdf.output_dir
    dpi = args.dpi if args.dpi is not None else config.pdf.dpi
    controller = RenderController(PyMuPdfRenderer())
    result = controller.render(pdf_path, output_dir, dpi)
    print_render_result(result)
    return 0


def _run_propose_crops(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pdf_path = _resolve_pdf(args, config)
    pages_dir = args.pages_dir if args.pages_dir is not None else config.pdf.output_dir
    dpi = args.dpi if args.dpi is not None else config.pdf.dpi
    crop = build_crop_controller(config)
    crop.propose_for_pdf(pdf_path, pages_dir, dpi)
    crop.confirm_loop(pages_dir, force_yes=bool(args.yes))
    print(f"Crops ready under {crop.crops_dir}")
    return 0


def _run_recrop(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pages_dir = args.pages_dir if args.pages_dir is not None else config.pdf.output_dir
    crop = build_crop_controller(config)
    result = crop.recrop_all(pages_dir)
    if not result.pages:
        print(f"No page_*_regions.json found under {crop.crops_dir}")
        return 1
    crop.confirm_loop(pages_dir, force_yes=bool(args.yes))
    print(f"Recropped {len(result.pages)} page(s) under {crop.crops_dir}")
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

    render_result = RenderController(PyMuPdfRenderer()).render(pdf_path, pages_dir, dpi)
    crop = build_crop_controller(config, recognition_dir)
    crop.ensure_crops_confirmed(
        render_result.pages,
        pages_dir,
        use_existing=bool(getattr(args, "use_existing_crops", False)),
        force_yes=bool(getattr(args, "yes", False)),
    )

    result = build_recognize_controller(config, recognition_dir).recognize_pages(
        render_result.pages,
        pages_dir,
        recognition_dir,
        from_crops=True,
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
        return build_recognize_controller(config, recognition_dir).recognize(
            pdf_path=pdf_path,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            dpi=dpi,
        )

    controller = ExtractController(
        extractor=QuestionExtractor(
            exam_schema=load_exam_schema(config.grading.standard_dir),
        ),
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


def _run_ingest_kunci(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    standard_dir = (
        args.standard if args.standard is not None else config.grading.standard_dir
    )
    kunci_dir = (
        args.kunci_dir
        if args.kunci_dir is not None
        else config.input.kunci_jawaban_dir
    )
    result = IngestKunciController().ingest(
        kunci_path=args.kunci,
        kunci_dir=kunci_dir,
        standard_dir=standard_dir,
    )
    print_ingest_kunci_result(result)
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = (
        args.questions_dir
        if args.questions_dir is not None
        else config.questions.output_dir
    )
    controller = ValidateController(build_validator(config))
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
    controller = build_grade_controller(config, standard_dir)
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
    controller = build_report_controller(config, standard_dir)
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

    interactive = sys.stdin.isatty()
    last_code = 0

    while True:
        try:
            pdf_path = _resolve_pdf(args, config)
            last_code = _process_one_pdf(config, args, pdf_path)
        except MathGraderError as exc:
            print_error(exc)
            last_code = 1
        except Exception as exc:  # noqa: BLE001 — CLI boundary maps unexpected → exit 2
            print_error(exc)
            last_code = 2

        if not interactive:
            return last_code

        action = prompt_continue_or_exit()
        if action == "exit":
            mark_interactive_session_done()
            return last_code
        args.pdf = None


if __name__ == "__main__":
    reset_interactive_session_flag()
    try:
        raise SystemExit(main())
    finally:
        wait_for_exit()
