"""Keep the console open and prompt for continue/exit after process."""

from __future__ import annotations

import sys

from app.functions.menu_choices import ContinueOrExit, parse_continue_or_exit
from app.views.prompt_view import read_line
from app.views.style import bold, box, cyan, dim

# Set by CLI after an interactive process session already dismissed the user.
_skip_wait_for_exit = False


def mark_interactive_session_done() -> None:
    global _skip_wait_for_exit
    _skip_wait_for_exit = True


def reset_interactive_session_flag() -> None:
    global _skip_wait_for_exit
    _skip_wait_for_exit = False


def wait_for_exit() -> None:
    """Block until Enter when stdin is an interactive terminal."""
    if _skip_wait_for_exit:
        return
    if not sys.stdin.isatty():
        return
    read_line(dim("\nTekan Enter untuk keluar..."))


def prompt_continue_or_exit() -> ContinueOrExit:
    """Ask whether to process another PDF or exit. Non-TTY → exit."""
    if not sys.stdin.isatty():
        return "exit"

    lines = [
        bold("Selesai."),
        "  1. Proses PDF lain",
        "  2. Keluar",
    ]
    print()
    print(cyan(box(lines)))

    while True:
        raw = read_line("Pilihan [1/2]: ")
        if raw is None:
            return "exit"
        try:
            return parse_continue_or_exit(raw)
        except ValueError:
            print(dim("Masukkan 1 (proses PDF lain) atau 2 (keluar)."))
