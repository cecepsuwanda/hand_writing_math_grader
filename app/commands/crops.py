"""Crop and question-label subcommands."""

from __future__ import annotations

import argparse

from app.commands import flows
from app.commands.base import (
    LABEL_YES_HELP,
    Command,
    add_dpi_arg,
    add_pages_dir_arg,
    add_pdf_arg,
    add_run_arg,
    add_topic_arg,
    add_yes_arg,
)
from app.config import load_config
from app.models.question_crops import LabelMode


class ProposeCropsCommand(Command):
    name = "propose-crops"
    help = "Ink-propose region boxes, write page_*_regions.json, crop PNGs, confirm"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_pdf_arg(parser)
        add_pages_dir_arg(parser)
        add_dpi_arg(parser)
        add_yes_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        pdf_path = flows.resolve_pdf(args, config)
        flows.propose_crops(
            config,
            flows.layout_for(config, pdf_path),
            pdf_path,
            pages_dir=args.pages_dir,
            dpi=args.dpi,
            force_yes=bool(args.yes),
        )
        return 0


class RecropCommand(Command):
    name = "recrop"
    help = "Re-crop PNGs from editable page_*_regions.json under crops/"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_pages_dir_arg(parser)
        add_yes_arg(parser, "Skip interactive crop confirmation after recrop")
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        flows.recrop(
            config,
            flows.layout_for_run(config, args),
            pages_dir=args.pages_dir,
            force_yes=bool(args.yes),
        )
        return 0


class LabelCommand(Command):
    """``label-questions`` (recognize numbers) or ``relabel-questions`` (reload edits)."""

    def __init__(self, name: str, help: str, mode: LabelMode) -> None:
        self.name = name
        self.help = help
        self.mode = mode

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_yes_arg(parser, LABEL_YES_HELP)
        add_topic_arg(parser)
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        flows.label(
            config,
            flows.layout_for_run(config, args),
            self.mode,
            force_yes=bool(args.yes),
            topic_id=args.topic,
        )
        return 0
