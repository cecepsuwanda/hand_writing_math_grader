"""Keep the console open and prompt for continue/exit after process."""

from __future__ import annotations

import sys
from typing import Literal

from app.views.style import bold, box, cyan, dim

ContinueOrExit = Literal["continue", "exit"]

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
    try:
        input(dim("\nTekan Enter untuk keluar..."))
    except (EOFError, KeyboardInterrupt):
        print()


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
        try:
            raw = input("Pilihan [1/2]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "exit"
        if raw in {"1", "lanjut", "continue", "c", "y", "ya"}:
            return "continue"
        if raw in {"2", "keluar", "exit", "q", "n", "tidak"}:
            return "exit"
        print(dim("Masukkan 1 (proses PDF lain) atau 2 (keluar)."))
