"""Flows shared by CLI subcommands and the interactive menu.

Builders are looked up on :mod:`app.services.pipeline_factory` at call time so
tests can patch a single target regardless of which command uses them.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.config import AppConfig, require_vision_model
from app.controllers.menu_controller import exit_code_for
from app.exceptions import (
    AmbiguousKunciDirError,
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
    resolve_jawaban_pdf,
)
from app.functions.run_layout import (
    RunLayout,
    build_run_layout,
    layout_for_pdf,
    list_run_dirs,
    resolve_run_name,
)
from app.functions.recognition_artifact import prune_stale_recognition
from app.functions.workspace_reset import ensure_resettable_dir
from app.models.defaults import DEFAULT_STUDENT_ID
from app.models.question_crops import LabelMode
from app.models.recognition import RecognizeResult
from app.services import pipeline_factory
from app.topics.registry import get_pack, list_packs
from app.views.crop_view import print_crops_ready, print_recrop_result
from app.views.error_view import print_error
from app.views.progress_view import print_models, print_process_summary, print_progress
from app.views.prompt_view import is_interactive, prompt_choice
from app.views.question_crops_view import print_question_crops_missing
from app.views.result_view import print_ingest_kunci_result
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

logger = logging.getLogger(__name__)


def report_failure(exc: Exception, context: str) -> int:
    """Print ``exc`` and map it to an exit code; log a traceback for unexpected errors."""
    code = exit_code_for(exc)
    if code == 2:
        logger.exception("Unexpected error in %s", context)
    print_error(exc)
    return code


# --- argument resolution --------------------------------------------------------


def dpi(args: argparse.Namespace, config: AppConfig) -> int:
    value = getattr(args, "dpi", None)
    return value if value is not None else config.pdf.dpi


def standard_dir(args: argparse.Namespace, config: AppConfig) -> Path:
    """``--standard`` if given, else ``<standards_root>/topik_<bab>`` of ``--topic``/config."""
    return pipeline_factory.resolve_standard_dir(
        config,
        topic_id=getattr(args, "topic", None),
        standard_dir=getattr(args, "standard", None),
    )


def resolve_pdf(args: argparse.Namespace, config: AppConfig) -> Path:
    if getattr(args, "pdf", None) is None:
        return select_pdf_interactive(config.input.jawaban_dir)
    resolved = resolve_jawaban_pdf(args.pdf, config.input.jawaban_dir)
    if not resolved.is_file():
        raise PdfNotFoundError(resolved)
    return resolved


def layout_for(config: AppConfig, pdf_path: Path) -> RunLayout:
    return layout_for_pdf(config.output.root_dir, pdf_path)


def layout_for_run(config: AppConfig, args: argparse.Namespace) -> RunLayout:
    """Resolve ``--run``; else the only run folder; else interactive choice (TTY)."""
    output_root = config.output.root_dir
    raw = getattr(args, "run", None)
    if raw is not None and raw.strip():
        return build_run_layout(output_root, resolve_run_name(raw))
    return pick_existing_run(output_root)


def questions_dir_for_run(config: AppConfig, args: argparse.Namespace) -> Path:
    if args.questions_dir is not None:
        return args.questions_dir
    return layout_for_run(config, args).questions_dir


# --- interactive selection ------------------------------------------------------


def select_pdf_interactive(jawaban_dir: Path) -> Path:
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


def pick_existing_run(output_root: Path, *, hint: str | None = None) -> RunLayout:
    """``hint`` replaces the default ``--run`` advice (e.g. inside the menu)."""
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
    raise RunNotSpecifiedError(output_root, [run.name for run in runs], hint=hint)


def select_kunci_interactive(kunci_dir: Path) -> Path:
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


def resolve_kunci_from_dir(kunci_dir: Path) -> Path:
    """The only ``.tex`` in ``kunci_dir``; several → interactive choice (TTY) or error."""
    tex_files = list_kunci_tex(kunci_dir)
    if not tex_files:
        raise NoKunciTexError(kunci_dir)
    if len(tex_files) == 1:
        return tex_files[0]
    if is_interactive():
        return select_kunci_interactive(kunci_dir)
    raise AmbiguousKunciDirError(kunci_dir, [path.name for path in tex_files])


def select_topic_interactive(active_topic_id: str) -> str | None:
    """Chosen pack id, or ``None`` when the user cancels (EOF / Ctrl+C)."""
    packs = list_packs()
    print_topic_menu(packs, active_topic_id=active_topic_id)
    known = [p.id for p in packs]
    while True:
        raw = prompt_topic_choice()
        if raw is None:
            return None
        try:
            pack = get_pack(parse_topic_choice(raw, known))
        except (ValueError, UnknownTopicError) as exc:
            print_error(InvalidMenuSelectionError(str(exc)))
            continue
        print_selected_topic(pack)
        return pack.id


# --- flows shared by the menu and the subcommands -------------------------------


def ingest(
    config: AppConfig,
    *,
    kunci_path: Path | None,
    kunci_dir: Path,
    standard_dir: Path,
    topic_id: str | None,
) -> None:
    controller = pipeline_factory.build_ingest_kunci_controller(
        config, standard_dir, topic_id=topic_id
    )
    result = controller.ingest(
        kunci_path=kunci_path,
        kunci_dir=kunci_dir,
        standard_dir=standard_dir,
    )
    print_ingest_kunci_result(result)


def propose_crops(
    config: AppConfig,
    layout: RunLayout,
    pdf_path: Path,
    *,
    pages_dir: Path | None = None,
    dpi: int | None = None,
    force_yes: bool = False,
) -> None:
    pages_dir = pages_dir or layout.pages_dir
    removed = pipeline_factory.prepare_run_workspace(layout, pages_dir=pages_dir)
    print_output_cleared(layout.root, removed)
    crop = pipeline_factory.build_crop_controller(
        config, layout.recognition_dir, crops_dir=layout.crops_dir
    )
    crop.propose_for_pdf(pdf_path, pages_dir, dpi if dpi is not None else config.pdf.dpi)
    crop.confirm_loop(pages_dir, force_yes=force_yes)
    print_crops_ready(crop.crops_dir)


def recrop(
    config: AppConfig,
    layout: RunLayout,
    *,
    pages_dir: Path | None = None,
    force_yes: bool = False,
) -> None:
    pages_dir = pages_dir or layout.pages_dir
    crop = pipeline_factory.build_crop_controller(
        config, layout.recognition_dir, crops_dir=layout.crops_dir
    )
    result = crop.recrop_all(pages_dir)
    if not result.pages:
        raise NoRegionsJsonError(crop.crops_dir)
    crop.confirm_loop(pages_dir, force_yes=force_yes)
    print_recrop_result(page_count=len(result.pages), crops_dir=crop.crops_dir)


def recognize_from_crops(
    config: AppConfig,
    layout: RunLayout,
    pdf_path: Path,
    *,
    pages_dir: Path,
    recognition_dir: Path,
    dpi: int,
    use_existing_crops: bool = False,
    force_yes: bool = False,
    standard_dir: Path | None = None,
    topic_id: str | None = None,
) -> RecognizeResult:
    """Render → confirm crops → recognize each page from its approved crops.

    Recognition of pages no longer in the PDF is dropped only after recognition
    succeeds, so a failed rerun keeps the prior JSON.
    """
    require_vision_model(config)
    ensure_resettable_dir(recognition_dir, run_root=layout.root, label="recognition")
    render_result = pipeline_factory.build_render_controller().render(
        pdf_path, pages_dir, dpi
    )
    crop = pipeline_factory.build_crop_controller(
        config,
        recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=standard_dir,
        topic_id=topic_id,
    )
    crop.ensure_crops_confirmed(
        render_result.pages,
        pages_dir,
        use_existing=use_existing_crops,
        force_yes=force_yes,
    )
    result = pipeline_factory.build_recognize_controller(
        config,
        recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=standard_dir,
        topic_id=topic_id,
    ).recognize_pages(
        render_result.pages,
        pages_dir,
        recognition_dir,
        from_crops=True,
    )
    prune_stale_recognition(recognition_dir, [p.page_number for p in render_result.pages])
    return result


def label(
    config: AppConfig,
    layout: RunLayout,
    mode: LabelMode,
    *,
    force_yes: bool = False,
    topic_id: str | None = None,
) -> None:
    controller = pipeline_factory.build_question_label_controller(
        config, layout.crops_dir, topic_id=topic_id
    )
    result = controller.label_all() if mode is LabelMode.LABEL else controller.reload_all()
    controller.confirm_loop(result, force_yes=force_yes)


def finish_from_crops(
    config: AppConfig, layout: RunLayout, *, topic_id: str | None = None
) -> None:
    print_models(
        vision_model=config.ollama.vision_model,
        reasoning_model=config.ollama.reasoning_model,
    )
    controller = pipeline_factory.build_process_controller(
        config,
        recognition_dir=layout.recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=pipeline_factory.resolve_standard_dir(config, topic_id=topic_id),
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
        workspace_root=layout.root,
    )
    print_process_summary(result)


def finish_from_questions(
    config: AppConfig,
    layout: RunLayout,
    *,
    topic_id: str | None = None,
    force_yes: bool = False,
) -> None:
    controller = pipeline_factory.build_process_controller(
        config,
        recognition_dir=layout.recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=pipeline_factory.resolve_standard_dir(config, topic_id=topic_id),
        topic_id=topic_id,
        on_progress=print_progress,
    )
    result = controller.process_from_questions(
        questions_dir=layout.questions_dir,
        output_dir=layout.report_dir,
        pages_dir=layout.pages_dir,
        recognition_dir=layout.recognition_dir,
        student_id=DEFAULT_STUDENT_ID,
        crops_dir=layout.crops_dir,
        force_yes=force_yes,
    )
    print_process_summary(result)


def process_one_pdf(config: AppConfig, args: argparse.Namespace, pdf_path: Path) -> int:
    """Run a single end-to-end process for ``pdf_path``; return exit code."""
    layout = layout_for(config, pdf_path)
    pages_dir = getattr(args, "pages_dir", None) or layout.pages_dir
    recognition_dir = getattr(args, "recognition_dir", None) or layout.recognition_dir
    questions_dir = getattr(args, "questions_dir", None) or layout.questions_dir
    output_dir = getattr(args, "output", None) or layout.report_dir
    use_existing_crops = bool(getattr(args, "use_existing_crops", False))

    removed = pipeline_factory.prepare_run_workspace(
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

    controller = pipeline_factory.build_process_controller(
        config,
        recognition_dir=recognition_dir,
        crops_dir=layout.crops_dir,
        standard_dir=standard_dir(args, config),
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
        dpi=dpi(args, config),
        student_id=getattr(args, "student_id", None) or DEFAULT_STUDENT_ID,
        workspace_root=layout.root,
        reset_workspace=False,
        crops_dir=layout.crops_dir,
        force_yes=bool(getattr(args, "yes", False)),
        use_existing_crops=use_existing_crops,
    )
    print_process_summary(result)
    return 0
