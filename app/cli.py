"""CLI bootstrap: parse args, wire dependencies, print results."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

from app.config import DEFAULT_CONFIG_PATH, AppConfig, load_config, require_vision_model
from app.controllers.menu_controller import MenuController, exit_code_for
from app.exceptions import (
    InteractiveTerminalRequiredError,
    InvalidKunciSelectionError,
    InvalidMenuSelectionError,
    InvalidPdfSelectionError,
    InvalidRunSelectionError,
    NoJawabanPdfError,
    NoKunciTexError,
    NoRegionsJsonError,
    PdfNotFoundError,
    RunNotSpecifiedError,
    UnknownTopicError,
)
from app.functions.menu_choices import parse_topic_choice
from app.functions.paths import (
    list_jawaban_pdfs,
    list_kunci_tex,
    parse_kunci_choice,
    parse_pdf_choice,
    parse_run_choice,
    resolve_input_path,
    resolve_jawaban_pdf,
)
from app.functions.run_layout import (
    RunLayout,
    build_run_layout,
    layout_for_pdf,
    list_run_dirs,
    resolve_run_name,
)
from app.functions.workspace_reset import clear_directory_contents
from app.models.defaults import DEFAULT_STUDENT_ID
from app.models.question_crops import LabelMode
from app.models.recognition import RecognizeResult
from app.services.pipeline_factory import (
    build_crop_controller,
    build_extract_controller,
    build_grade_controller,
    build_ingest_kunci_controller,
    build_latex_controller,
    build_process_controller,
    build_question_label_controller,
    build_recognize_controller,
    build_render_controller,
    build_report_controller,
    build_validate_controller,
    prepare_run_workspace,
)
from app.topics.registry import get_pack, list_packs
from app.views.crop_view import print_crops_ready, print_recrop_result
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
from app.views.prompt_view import is_interactive, prompt_choice
from app.views.question_crops_view import print_question_crops_missing
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
    print_output_cleared,
    print_run_menu,
    print_selected_kunci,
    print_selected_pdf,
    print_selected_run,
    print_selected_topic,
    print_topic_menu,
    prompt_topic_choice,
)
from app.views.style import configure_console_streams

logger = logging.getLogger(__name__)

_PAGES_HELP = "Directory for page PNGs (default: <output.root_dir>/<nama_pdf>/pages)"
_DPI_HELP = "Render DPI (default: config pdf.dpi)"
_CROP_YES_HELP = "Skip interactive crop confirmation"
_LABEL_YES_HELP = "Skip interactive confirmation of question numbers"
_STANDARD_HELP = "Standards directory (default: config grading.standard_dir)"
_QUESTIONS_HELP = (
    "Directory with question_*/question.json "
    "(default: <output.root_dir>/<nama_pdf>/questions)"
)


# --- argparse -----------------------------------------------------------------


def _add_pdf_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "pdf",
        type=Path,
        help="Student answer PDF (searched under data/input/jawaban if needed)",
    )


def _add_output_arg(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument("--output", type=Path, default=None, help=help)


def _add_pages_dir_arg(parser: argparse.ArgumentParser, help: str = _PAGES_HELP) -> None:
    parser.add_argument("--pages-dir", type=Path, default=None, help=help)


def _add_dpi_arg(parser: argparse.ArgumentParser, help: str = _DPI_HELP) -> None:
    parser.add_argument("--dpi", type=int, default=None, help=help)


def _add_yes_arg(parser: argparse.ArgumentParser, help: str = _CROP_YES_HELP) -> None:
    parser.add_argument("--yes", "-y", action="store_true", help=help)


def _add_questions_dir_arg(
    parser: argparse.ArgumentParser, help: str = _QUESTIONS_HELP
) -> None:
    parser.add_argument("--questions-dir", type=Path, default=None, help=help)


def _add_standard_arg(parser: argparse.ArgumentParser, help: str = _STANDARD_HELP) -> None:
    parser.add_argument("--standard", type=Path, default=None, help=help)


def _add_student_id_arg(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument(
        "--student-id",
        type=str,
        default=DEFAULT_STUDENT_ID,
        help=f"{help} (default: {DEFAULT_STUDENT_ID})",
    )


def _add_run_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run",
        type=str,
        default=None,
        help=(
            "Run folder under config output.root_dir (folder name or PDF filename); "
            "default: the only run folder, or interactive choice"
        ),
    )


def _add_topic_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Topic pack id (default: config grading.topic_id or exam_schema)",
    )


Subparsers = argparse._SubParsersAction  # noqa: SLF001 — argparse exposes no public alias


def _add_render_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser("render", help="Render a PDF to per-page PNG images")
    _add_pdf_arg(parser)
    _add_output_arg(parser, _PAGES_HELP)
    _add_dpi_arg(parser)


def _add_recognize_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "recognize", help="Render a PDF and run Ollama vision recognition"
    )
    _add_pdf_arg(parser)
    _add_output_arg(
        parser,
        "Directory for recognition JSON (default: <output.root_dir>/<nama_pdf>/recognition)",
    )
    _add_pages_dir_arg(parser)
    _add_dpi_arg(parser)
    _add_yes_arg(parser)
    parser.add_argument(
        "--use-existing-crops",
        action="store_true",
        help="Reuse existing page_*_regions.json instead of re-running ink propose",
    )


def _add_propose_crops_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "propose-crops",
        help="Ink-propose region boxes, write page_*_regions.json, crop PNGs, confirm",
    )
    _add_pdf_arg(parser)
    _add_pages_dir_arg(parser)
    _add_dpi_arg(parser)
    _add_yes_arg(parser)


def _add_recrop_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "recrop", help="Re-crop PNGs from editable page_*_regions.json under crops/"
    )
    _add_pages_dir_arg(parser)
    _add_yes_arg(parser, "Skip interactive crop confirmation after recrop")
    _add_run_arg(parser)


def _add_label_parsers(subparsers: Subparsers) -> None:
    label = subparsers.add_parser(
        "label-questions",
        help="Recognize question numbers per crop → crops/question_crops/question_*.json",
    )
    _add_yes_arg(label, _LABEL_YES_HELP)
    _add_run_arg(label)

    relabel = subparsers.add_parser(
        "relabel-questions",
        help="Reload edited question_crops/question_*.json and validate",
    )
    _add_yes_arg(relabel, _LABEL_YES_HELP)
    _add_run_arg(relabel)


def _add_extract_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "extract", help="Merge recognition JSON into per-question artifacts"
    )
    _add_pdf_arg(parser)
    _add_output_arg(
        parser,
        "Directory for question artifacts (default: <output.root_dir>/<nama_pdf>/questions)",
    )
    parser.add_argument(
        "--recognition-dir",
        type=Path,
        default=None,
        help=(
            "Directory with page_*_recognition.json "
            "(default: <output.root_dir>/<nama_pdf>/recognition)"
        ),
    )
    _add_pages_dir_arg(parser, "Directory for page PNGs if recognition must run first")
    _add_dpi_arg(parser, "Render DPI if recognition must run first")
    parser.add_argument(
        "--force-recognize",
        action="store_true",
        help="Always run recognition before extract, even if JSON exists",
    )


def _add_latex_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "latex", help="Build student.tex from extracted question.json files"
    )
    _add_questions_dir_arg(parser)
    _add_run_arg(parser)


def _add_validate_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "validate", help="Validate student steps with SymPy (writes validation.json)"
    )
    _add_questions_dir_arg(parser)
    _add_topic_arg(parser)
    _add_run_arg(parser)


def _add_grade_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "grade", help="Grade validated questions against a rubric standard"
    )
    _add_questions_dir_arg(
        parser, "Directory with question_*/ (default: <output.root_dir>/<nama_pdf>/questions)"
    )
    _add_standard_arg(parser)
    _add_topic_arg(parser)
    _add_run_arg(parser)


def _add_report_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "report", help="Build JSON/CSV/HTML/LaTeX report from grading.json artifacts"
    )
    _add_questions_dir_arg(
        parser,
        "Directory with question_*/grading.json "
        "(default: <output.root_dir>/<nama_pdf>/questions)",
    )
    _add_output_arg(
        parser, "Output directory for report files (default: <output.root_dir>/<nama_pdf>)"
    )
    _add_student_id_arg(parser, "Student identifier for summary CSV")
    _add_standard_arg(
        parser, "Standards directory recorded in metadata (default: config grading.standard_dir)"
    )
    _add_run_arg(parser)


def _add_process_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "process",
        help="Run full pipeline: render → recognize → extract → latex → validate → grade → report",
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        default=None,
        type=Path,
        help=(
            "Student answer PDF under data/input/jawaban "
            "(omit to choose interactively from that folder)"
        ),
    )
    _add_standard_arg(parser)
    _add_output_arg(parser, "Report output directory (default: <output.root_dir>/<nama_pdf>)")
    _add_student_id_arg(parser, "Student identifier")
    _add_dpi_arg(parser)
    _add_pages_dir_arg(parser)
    parser.add_argument(
        "--recognition-dir",
        type=Path,
        default=None,
        help="Directory for recognition JSON (default: <output.root_dir>/<nama_pdf>/recognition)",
    )
    _add_questions_dir_arg(
        parser,
        "Directory for question artifacts (default: <output.root_dir>/<nama_pdf>/questions)",
    )
    _add_yes_arg(parser)
    parser.add_argument(
        "--use-existing-crops",
        action="store_true",
        help="Reuse existing page_*_regions.json (skip ink re-propose)",
    )
    _add_topic_arg(parser)


def _add_ingest_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "ingest-kunci", help="Ingest kunci_jawaban TeX into standards/solutions"
    )
    parser.add_argument(
        "kunci",
        type=Path,
        nargs="?",
        default=None,
        help="Kunci .tex file (default: all .tex under config input.kunci_jawaban_dir)",
    )
    _add_standard_arg(parser)
    parser.add_argument(
        "--kunci-dir",
        type=Path,
        default=None,
        help="Directory of kunci .tex files (default: config input.kunci_jawaban_dir)",
    )
    _add_topic_arg(parser)


def _add_menu_parser(subparsers: Subparsers) -> None:
    parser = subparsers.add_parser(
        "menu",
        help=(
            "Interactive main menu (topic / ingest kunci / crop / recrop / "
            "label questions / reload labels / grade from crops / exit)"
        ),
    )
    _add_topic_arg(parser)


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
    for add in (
        _add_render_parser,
        _add_recognize_parser,
        _add_propose_crops_parser,
        _add_recrop_parser,
        _add_label_parsers,
        _add_extract_parser,
        _add_latex_parser,
        _add_validate_parser,
        _add_grade_parser,
        _add_report_parser,
        _add_process_parser,
        _add_ingest_parser,
        _add_menu_parser,
    ):
        add(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _HANDLERS[args.command](args)
    except Exception as exc:  # noqa: BLE001 — CLI boundary maps unexpected → exit 2
        return _report_failure(exc, args.command)


def _report_failure(exc: Exception, context: str) -> int:
    code = exit_code_for(exc)
    if code == 2:
        logger.exception("Unexpected error in %s", context)
    print_error(exc)
    return code


# --- argument resolution --------------------------------------------------------


def _dpi(args: argparse.Namespace, config: AppConfig) -> int:
    dpi = getattr(args, "dpi", None)
    return dpi if dpi is not None else config.pdf.dpi


def _standard_dir(args: argparse.Namespace, config: AppConfig) -> Path:
    return getattr(args, "standard", None) or config.grading.standard_dir


def _resolve_pdf(args: argparse.Namespace, config: AppConfig) -> Path:
    if getattr(args, "pdf", None) is None:
        return _select_pdf_interactive(config.input.jawaban_dir)
    resolved = resolve_jawaban_pdf(args.pdf, config.input.jawaban_dir)
    if not resolved.is_file():
        raise PdfNotFoundError(resolved)
    return resolved


def _layout_for_pdf(config: AppConfig, pdf_path: Path) -> RunLayout:
    return layout_for_pdf(config.output.root_dir, pdf_path)


def _layout_for_run(config: AppConfig, args: argparse.Namespace) -> RunLayout:
    """Resolve ``--run``; else the only run folder; else interactive choice (TTY)."""
    output_root = config.output.root_dir
    raw = getattr(args, "run", None)
    if raw is not None and raw.strip():
        return build_run_layout(output_root, resolve_run_name(raw))
    return _pick_existing_run(output_root)


def _questions_dir_for_run(config: AppConfig, args: argparse.Namespace) -> Path:
    if args.questions_dir is not None:
        return args.questions_dir
    return _layout_for_run(config, args).questions_dir


# --- interactive selection ------------------------------------------------------


def _select_pdf_interactive(jawaban_dir: Path) -> Path:
    pdfs = list_jawaban_pdfs(jawaban_dir)
    if not pdfs:
        raise NoJawabanPdfError(jawaban_dir)
    print_jawaban_menu(pdfs, jawaban_dir)
    return prompt_choice(
        pdfs,
        parse=parse_pdf_choice,
        error_cls=InvalidPdfSelectionError,
        on_selected=print_selected_pdf,
    )


def _pick_existing_run(output_root: Path) -> RunLayout:
    runs = list_run_dirs(output_root)
    if len(runs) == 1:
        return RunLayout(root=runs[0])
    if runs and is_interactive():
        print_run_menu(runs, output_root)
        selected = prompt_choice(
            runs,
            parse=parse_run_choice,
            error_cls=InvalidRunSelectionError,
            on_selected=print_selected_run,
        )
        return RunLayout(root=selected)
    raise RunNotSpecifiedError(output_root, [run.name for run in runs])


def _select_kunci_interactive(kunci_dir: Path) -> Path:
    tex_files = list_kunci_tex(kunci_dir)
    if not tex_files:
        raise NoKunciTexError(kunci_dir)
    print_kunci_menu(tex_files, kunci_dir)
    return prompt_choice(
        tex_files,
        parse=parse_kunci_choice,
        error_cls=InvalidKunciSelectionError,
        on_selected=print_selected_kunci,
    )


def _select_topic_interactive(active_topic_id: str) -> str:
    packs = list_packs()
    print_topic_menu(packs, active_topic_id=active_topic_id)
    known = [p.id for p in packs]
    while True:
        raw = prompt_topic_choice()
        if raw is None:
            return active_topic_id
        try:
            pack = get_pack(parse_topic_choice(raw, known))
        except (ValueError, UnknownTopicError) as exc:
            print_error(InvalidMenuSelectionError(str(exc)))
            continue
        print_selected_topic(pack)
        return pack.id


# --- flows shared by the menu and the subcommands -------------------------------


def _ingest(
    config: AppConfig,
    *,
    kunci_path: Path | None,
    kunci_dir: Path,
    standard_dir: Path,
    topic_id: str | None,
) -> None:
    result = build_ingest_kunci_controller(config, standard_dir, topic_id=topic_id).ingest(
        kunci_path=kunci_path,
        kunci_dir=kunci_dir,
        standard_dir=standard_dir,
    )
    print_ingest_kunci_result(result)


def _propose_crops(
    config: AppConfig,
    layout: RunLayout,
    pdf_path: Path,
    *,
    pages_dir: Path | None = None,
    dpi: int | None = None,
    force_yes: bool = False,
) -> None:
    pages_dir = pages_dir or layout.pages_dir
    removed = prepare_run_workspace(layout, pages_dir=pages_dir)
    print_output_cleared(layout.root, removed)
    crop = build_crop_controller(config, layout.recognition_dir, crops_dir=layout.crops_dir)
    crop.propose_for_pdf(pdf_path, pages_dir, dpi if dpi is not None else config.pdf.dpi)
    crop.confirm_loop(pages_dir, force_yes=force_yes)
    print_crops_ready(crop.crops_dir)


def _recrop(
    config: AppConfig,
    layout: RunLayout,
    *,
    pages_dir: Path | None = None,
    force_yes: bool = False,
) -> None:
    pages_dir = pages_dir or layout.pages_dir
    crop = build_crop_controller(config, layout.recognition_dir, crops_dir=layout.crops_dir)
    result = crop.recrop_all(pages_dir)
    if not result.pages:
        raise NoRegionsJsonError(crop.crops_dir)
    crop.confirm_loop(pages_dir, force_yes=force_yes)
    print_recrop_result(page_count=len(result.pages), crops_dir=crop.crops_dir)


def _label(
    config: AppConfig, layout: RunLayout, mode: LabelMode, *, force_yes: bool = False
) -> None:
    controller = build_question_label_controller(config, layout.crops_dir)
    result = controller.label_all() if mode is LabelMode.LABEL else controller.reload_all()
    controller.confirm_loop(result, force_yes=force_yes)


def _finish_from_crops(
    config: AppConfig, layout: RunLayout, *, topic_id: str | None = None
) -> None:
    print_models(
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )
    controller = build_process_controller(
        config,
        recognition_dir=layout.recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=config.grading.standard_dir,
        topic_id=topic_id,
        on_progress=print_progress,
        on_question_crops_missing=print_question_crops_missing,
    )
    result = controller.process_from_crops(
        pages_dir=layout.pages_dir,
        recognition_dir=layout.recognition_dir,
        questions_dir=layout.questions_dir,
        output_dir=layout.report_dir,
        student_id=DEFAULT_STUDENT_ID,
        crops_dir=layout.crops_dir,
    )
    print_process_summary(result)


def _process_one_pdf(config: AppConfig, args: argparse.Namespace, pdf_path: Path) -> int:
    """Run a single end-to-end process for ``pdf_path``; return exit code."""
    layout = _layout_for_pdf(config, pdf_path)
    pages_dir = getattr(args, "pages_dir", None) or layout.pages_dir
    recognition_dir = getattr(args, "recognition_dir", None) or layout.recognition_dir
    questions_dir = getattr(args, "questions_dir", None) or layout.questions_dir
    output_dir = getattr(args, "output", None) or layout.report_dir
    use_existing_crops = bool(getattr(args, "use_existing_crops", False))

    removed = prepare_run_workspace(
        layout,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        preserve_crops=use_existing_crops,
    )
    print_output_cleared(layout.root, removed)
    print_models(
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )

    controller = build_process_controller(
        config,
        recognition_dir=recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=_standard_dir(args, config),
        topic_id=getattr(args, "topic", None),
        on_progress=print_progress,
        on_question_crops_missing=print_question_crops_missing,
    )
    result = controller.process(
        pdf_path,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        output_dir=output_dir,
        dpi=_dpi(args, config),
        student_id=getattr(args, "student_id", None) or DEFAULT_STUDENT_ID,
        workspace_root=layout.root,
        reset_workspace=False,
        crops_dir=layout.crops_dir,
        force_yes=bool(getattr(args, "yes", False)),
        use_existing_crops=use_existing_crops,
    )
    print_process_summary(result)
    return 0


# --- interactive menu -----------------------------------------------------------


class _CliMenuActions:
    """:class:`MenuActions` backed by the CLI flows above."""

    def select_topic(self, active_topic_id: str) -> str:
        return _select_topic_interactive(active_topic_id)

    def select_pdf(self, config: AppConfig) -> Path:
        return _select_pdf_interactive(config.input.jawaban_dir)

    def pick_run(self, config: AppConfig) -> RunLayout:
        return _pick_existing_run(config.output.root_dir)

    def ingest(self, config: AppConfig, topic_id: str) -> None:
        kunci_dir = config.input.kunci_jawaban_dir
        _ingest(
            config,
            kunci_path=_select_kunci_interactive(kunci_dir),
            kunci_dir=kunci_dir,
            standard_dir=config.grading.standard_dir,
            topic_id=topic_id,
        )

    def propose_crops(self, config: AppConfig, layout: RunLayout, pdf_path: Path) -> None:
        _propose_crops(config, layout, pdf_path)

    def recrop(self, config: AppConfig, layout: RunLayout) -> None:
        _recrop(config, layout)

    def label(self, config: AppConfig, layout: RunLayout, mode: LabelMode) -> None:
        _label(config, layout, mode)

    def finish(self, config: AppConfig, layout: RunLayout, topic_id: str | None) -> None:
        _finish_from_crops(config, layout, topic_id=topic_id)


# --- subcommand handlers ----------------------------------------------------------


def _run_menu(args: argparse.Namespace) -> int:
    if not is_interactive():
        raise InteractiveTerminalRequiredError()
    config = load_config(args.config)
    return MenuController(
        _CliMenuActions(), config, topic_id=getattr(args, "topic", None)
    ).run()


def _run_render(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pdf_path = _resolve_pdf(args, config)
    output_dir = args.output or _layout_for_pdf(config, pdf_path).pages_dir
    result = build_render_controller().render(pdf_path, output_dir, _dpi(args, config))
    print_render_result(result)
    return 0


def _run_propose_crops(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pdf_path = _resolve_pdf(args, config)
    _propose_crops(
        config,
        _layout_for_pdf(config, pdf_path),
        pdf_path,
        pages_dir=args.pages_dir,
        dpi=args.dpi,
        force_yes=bool(args.yes),
    )
    return 0


def _run_recrop(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    _recrop(
        config,
        _layout_for_run(config, args),
        pages_dir=args.pages_dir,
        force_yes=bool(args.yes),
    )
    return 0


def _label_handler(mode: LabelMode) -> Callable[[argparse.Namespace], int]:
    def handler(args: argparse.Namespace) -> int:
        config = load_config(args.config)
        _label(config, _layout_for_run(config, args), mode, force_yes=bool(args.yes))
        return 0

    return handler


def _run_recognize(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    require_vision_model(config)

    pdf_path = _resolve_pdf(args, config)
    layout = _layout_for_pdf(config, pdf_path)
    pages_dir = args.pages_dir or layout.pages_dir
    recognition_dir = args.output or layout.recognition_dir

    render_result = build_render_controller().render(pdf_path, pages_dir, _dpi(args, config))
    crop = build_crop_controller(config, recognition_dir, crops_dir=layout.crops_dir)
    crop.ensure_crops_confirmed(
        render_result.pages,
        pages_dir,
        use_existing=bool(args.use_existing_crops),
        force_yes=bool(args.yes),
    )

    clear_directory_contents(recognition_dir)
    result = build_recognize_controller(
        config, recognition_dir, crops_dir=layout.crops_dir
    ).recognize_pages(
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
    layout = _layout_for_pdf(config, pdf_path)
    recognition_dir = args.recognition_dir or layout.recognition_dir
    output_dir = args.output or layout.questions_dir
    pages_dir = args.pages_dir or layout.pages_dir
    dpi = _dpi(args, config)

    def recognize_runner() -> RecognizeResult:
        require_vision_model(config)
        clear_directory_contents(recognition_dir)
        return build_recognize_controller(
            config, recognition_dir, crops_dir=layout.crops_dir
        ).recognize(
            pdf_path=pdf_path,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            dpi=dpi,
        )

    controller = build_extract_controller(config, recognize_runner=recognize_runner)
    clear_directory_contents(output_dir)
    result = controller.extract(
        recognition_dir=recognition_dir,
        output_dir=output_dir,
        force_recognize=bool(args.force_recognize),
    )
    print_extract_result(result)
    return 0


def _run_latex(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = build_latex_controller().build(_questions_dir_for_run(config, args))
    print_latex_result(result)
    return 0


def _run_ingest_kunci(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    kunci_dir = args.kunci_dir or config.input.kunci_jawaban_dir
    _ingest(
        config,
        kunci_path=(
            resolve_input_path(args.kunci, kunci_dir) if args.kunci is not None else None
        ),
        kunci_dir=kunci_dir,
        standard_dir=_standard_dir(args, config),
        topic_id=args.topic,
    )
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = _questions_dir_for_run(config, args)
    result = build_validate_controller(config, topic_id=args.topic).validate(questions_dir)
    print_validate_result(result)
    return 0


def _run_grade(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    questions_dir = _questions_dir_for_run(config, args)
    controller = build_grade_controller(
        config, _standard_dir(args, config), topic_id=args.topic
    )
    print_grade_result(controller.grade(questions_dir))
    return 0


def _run_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    has_run = bool((args.run or "").strip())
    if args.questions_dir is not None and not has_run:
        # questions/ sits directly under its run root next to crops/.
        layout = RunLayout(root=Path(args.questions_dir).parent)
    else:
        layout = _layout_for_run(config, args)
    controller = build_report_controller(config, _standard_dir(args, config))
    result = controller.report(
        args.questions_dir or layout.questions_dir,
        args.output or layout.report_dir,
        student_id=args.student_id,
        crops_dir=layout.crops_dir,
    )
    print_report_result(result)
    return 0


_PER_PDF_OVERRIDES = ("pdf", "pages_dir", "recognition_dir", "questions_dir", "output")


def _run_process(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    require_vision_model(config)

    interactive = is_interactive()
    last_code = 0
    while True:
        try:
            last_code = _process_one_pdf(config, args, _resolve_pdf(args, config))
        except Exception as exc:  # noqa: BLE001 — keep the interactive loop alive
            last_code = _report_failure(exc, "process")

        if not interactive:
            return last_code
        if prompt_continue_or_exit() == "exit":
            mark_interactive_session_done()
            return last_code
        # Path overrides belong to the first PDF; reusing them would make the
        # next run clear and overwrite the previous PDF's artifacts.
        for name in _PER_PDF_OVERRIDES:
            setattr(args, name, None)


_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "render": _run_render,
    "recognize": _run_recognize,
    "propose-crops": _run_propose_crops,
    "recrop": _run_recrop,
    "label-questions": _label_handler(LabelMode.LABEL),
    "relabel-questions": _label_handler(LabelMode.RELABEL),
    "extract": _run_extract,
    "latex": _run_latex,
    "validate": _run_validate,
    "grade": _run_grade,
    "report": _run_report,
    "process": _run_process,
    "ingest-kunci": _run_ingest_kunci,
    "menu": _run_menu,
}


if __name__ == "__main__":
    configure_console_streams()
    reset_interactive_session_flag()
    try:
        raise SystemExit(main())
    finally:
        wait_for_exit()
