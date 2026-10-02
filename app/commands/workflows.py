"""Multi-stage subcommands: process, finish-questions, ingest-kunci, menu."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.commands import flows
from app.commands.base import (
    Command,
    add_dpi_arg,
    add_output_arg,
    add_pages_dir_arg,
    add_questions_dir_arg,
    add_run_arg,
    add_standard_arg,
    add_student_id_arg,
    add_topic_arg,
    add_use_existing_crops_arg,
    add_yes_arg,
)
from app.commands.menu_actions import CliMenuActions
from app.config import load_config, require_vision_model
from app.controllers.menu_controller import MenuController
from app.exceptions import InteractiveTerminalRequiredError, KunciNotFoundError
from app.functions.paths import resolve_input_path
from app.views.exit_view import mark_interactive_session_done, prompt_continue_or_exit
from app.views.prompt_view import is_interactive

_PER_PDF_OVERRIDES = (
    "pdf",
    "pages_dir",
    "recognition_dir",
    "questions_dir",
    "output",
    "student_id",
)


class ProcessCommand(Command):
    name = "process"
    help = "Run full pipeline: render → recognize → extract → latex → validate → grade → report"

    def configure(self, parser: argparse.ArgumentParser) -> None:
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
        add_standard_arg(parser)
        add_output_arg(
            parser, "Report output directory (default: <output.root_dir>/<nama_pdf>)"
        )
        add_student_id_arg(parser, "Student identifier")
        add_dpi_arg(parser)
        add_pages_dir_arg(parser)
        parser.add_argument(
            "--recognition-dir",
            type=Path,
            default=None,
            help=(
                "Directory for recognition JSON "
                "(default: <output.root_dir>/<nama_pdf>/recognition)"
            ),
        )
        add_questions_dir_arg(
            parser,
            "Directory for question artifacts (default: <output.root_dir>/<nama_pdf>/questions)",
        )
        add_yes_arg(parser)
        add_use_existing_crops_arg(
            parser, "Reuse existing page_*_regions.json (skip ink re-propose)"
        )
        add_topic_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        require_vision_model(config)

        interactive = is_interactive()
        last_code = 0
        while True:
            try:
                last_code = flows.process_one_pdf(config, args, flows.resolve_pdf(args, config))
            except Exception as exc:  # noqa: BLE001 — keep the interactive loop alive
                last_code = flows.report_failure(exc, self.name)

            if not interactive:
                return last_code
            if prompt_continue_or_exit() == "exit":
                mark_interactive_session_done()
                return last_code
            # Path overrides belong to the first PDF; reusing them would make the
            # next run clear and overwrite the previous PDF's artifacts.
            for name in _PER_PDF_OVERRIDES:
                setattr(args, name, None)


class FinishQuestionsCommand(Command):
    name = "finish-questions"
    help = (
        "Review edited questions/question_*/question.json, then "
        "latex → validate → grade → report (no recognize, no rewrite)"
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_yes_arg(parser, "Skip the interactive transcription review")
        add_topic_arg(parser)
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        flows.finish_from_questions(
            config,
            flows.layout_for_run(config, args),
            topic_id=args.topic,
            force_yes=bool(args.yes),
        )
        return 0


class IngestKunciCommand(Command):
    name = "ingest-kunci"
    help = "Ingest one kunci_jawaban TeX into standards/topik_<bab> of the topic"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "kunci",
            type=Path,
            nargs="?",
            default=None,
            help=(
                "Kunci .tex file (default: the only .tex under config "
                "input.kunci_jawaban_dir; if several, choose interactively)"
            ),
        )
        add_standard_arg(parser)
        parser.add_argument(
            "--kunci-dir",
            type=Path,
            default=None,
            help="Directory of kunci .tex files (default: config input.kunci_jawaban_dir)",
        )
        add_topic_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        kunci_dir = args.kunci_dir or config.input.kunci_jawaban_dir
        if args.kunci is not None:
            kunci_path = resolve_input_path(args.kunci, kunci_dir)
            if not kunci_path.is_file():
                raise KunciNotFoundError(kunci_path)
        else:
            kunci_path = flows.resolve_kunci_from_dir(kunci_dir)
        flows.ingest(
            config,
            kunci_path=kunci_path,
            kunci_dir=kunci_dir,
            standard_dir=flows.standard_dir(args, config),
            topic_id=args.topic,
        )
        return 0


class MenuCommand(Command):
    name = "menu"
    help = (
        "Interactive main menu (topic / ingest kunci / crop / recrop / "
        "label questions / reload labels / grade from crops / "
        "grade from edited question.json / exit)"
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_topic_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        if not is_interactive():
            raise InteractiveTerminalRequiredError()
        config = load_config(args.config)
        return MenuController(
            CliMenuActions(), config, topic_id=getattr(args, "topic", None)
        ).run()
