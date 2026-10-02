"""Command port for CLI subcommands + shared argparse argument helpers."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from pathlib import Path

from app.models.defaults import DEFAULT_STUDENT_ID

PAGES_HELP = "Directory for page PNGs (default: <output.root_dir>/<nama_pdf>/pages)"
DPI_HELP = "Render DPI (default: config pdf.dpi)"
CROP_YES_HELP = "Skip interactive crop confirmation"
LABEL_YES_HELP = "Skip interactive confirmation of question numbers"
STANDARD_HELP = (
    "Standards directory (default: <grading.standards_root>/topik_<bab> of the topic)"
)
QUESTIONS_HELP = (
    "Directory with question_*/question.json "
    "(default: <output.root_dir>/<nama_pdf>/questions)"
)


class Command(ABC):
    """One ``python -m app.cli <name>`` subcommand: its arguments and its handler."""

    name: str
    help: str

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Register subcommand arguments (default: none)."""

    @abstractmethod
    def run(self, args: argparse.Namespace) -> int:
        """Execute the subcommand; return the process exit code."""


def add_pdf_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "pdf",
        type=Path,
        help="Student answer PDF (searched under data/input/jawaban if needed)",
    )


def add_output_arg(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument("--output", type=Path, default=None, help=help)


def add_pages_dir_arg(parser: argparse.ArgumentParser, help: str = PAGES_HELP) -> None:
    parser.add_argument("--pages-dir", type=Path, default=None, help=help)


def add_dpi_arg(parser: argparse.ArgumentParser, help: str = DPI_HELP) -> None:
    parser.add_argument("--dpi", type=int, default=None, help=help)


def add_yes_arg(parser: argparse.ArgumentParser, help: str = CROP_YES_HELP) -> None:
    parser.add_argument("--yes", "-y", action="store_true", help=help)


def add_questions_dir_arg(
    parser: argparse.ArgumentParser, help: str = QUESTIONS_HELP
) -> None:
    parser.add_argument("--questions-dir", type=Path, default=None, help=help)


def add_standard_arg(parser: argparse.ArgumentParser, help: str = STANDARD_HELP) -> None:
    parser.add_argument("--standard", type=Path, default=None, help=help)


def add_student_id_arg(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument(
        "--student-id",
        type=str,
        default=DEFAULT_STUDENT_ID,
        help=f"{help} (default: {DEFAULT_STUDENT_ID})",
    )


def add_run_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run",
        type=str,
        default=None,
        help=(
            "Run folder under config output.root_dir (folder name or PDF filename); "
            "default: the only run folder, or interactive choice"
        ),
    )


def add_topic_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help=(
            "Topic pack id; also picks standards/topik_<bab> "
            "(default: config grading.topic_id)"
        ),
    )


def add_use_existing_crops_arg(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument("--use-existing-crops", action="store_true", help=help)
