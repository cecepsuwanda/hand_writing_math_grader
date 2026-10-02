"""CLI subcommands: one :class:`Command` per ``python -m app.cli <name>``.

``COMMANDS`` order is the order shown by ``--help``.
"""

from __future__ import annotations

from app.commands.base import Command
from app.commands.crops import LabelCommand, ProposeCropsCommand, RecropCommand
from app.commands.stages import (
    ExtractCommand,
    GradeCommand,
    LatexCommand,
    RecognizeCommand,
    RenderCommand,
    ReportCommand,
    ValidateCommand,
)
from app.commands.workflows import (
    FinishQuestionsCommand,
    IngestKunciCommand,
    MenuCommand,
    ProcessCommand,
)
from app.models.question_crops import LabelMode

COMMANDS: tuple[Command, ...] = (
    RenderCommand(),
    RecognizeCommand(),
    ProposeCropsCommand(),
    RecropCommand(),
    LabelCommand(
        "label-questions",
        "Recognize question numbers per crop → crops/question_crops/question_*.json",
        LabelMode.LABEL,
    ),
    LabelCommand(
        "relabel-questions",
        "Reload edited question_crops/question_*.json and validate",
        LabelMode.RELABEL,
    ),
    ExtractCommand(),
    LatexCommand(),
    ValidateCommand(),
    GradeCommand(),
    ReportCommand(),
    ProcessCommand(),
    FinishQuestionsCommand(),
    IngestKunciCommand(),
    MenuCommand(),
)

__all__ = ["COMMANDS", "Command"]
