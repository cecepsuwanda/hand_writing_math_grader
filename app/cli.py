"""CLI bootstrap: build the parser from ``COMMANDS``, dispatch, map errors to exit codes."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.commands import COMMANDS
from app.commands.flows import report_failure
from app.config import DEFAULT_CONFIG_PATH
from app.views.exit_view import reset_interactive_session_flag, wait_for_exit
from app.views.style import configure_console_streams

_COMMANDS_BY_NAME = {command.name: command for command in COMMANDS}


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
    for command in COMMANDS:
        command.configure(subparsers.add_parser(command.name, help=command.help))
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_console_streams()
    args = build_parser().parse_args(argv)
    try:
        return _COMMANDS_BY_NAME[args.command].run(args)
    except Exception as exc:  # noqa: BLE001 — CLI boundary maps unexpected → exit 2
        return report_failure(exc, args.command)


if __name__ == "__main__":
    reset_interactive_session_flag()
    try:
        raise SystemExit(main())
    finally:
        wait_for_exit()
