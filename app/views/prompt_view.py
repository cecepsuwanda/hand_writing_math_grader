"""Shared interactive prompts: line input, yes/no, pick-from-list, wait for edit."""

from __future__ import annotations

import builtins
import sys
from collections.abc import Callable, Sequence
from typing import TypeVar

from app.exceptions import MathGraderError, OperationCancelledError
from app.functions.menu_choices import parse_yes_no
from app.views.error_view import print_error

InputFn = Callable[[str], str]
T = TypeVar("T")
Item = TypeVar("Item")


def is_interactive(input_fn: InputFn | None = None) -> bool:
    """An explicit ``input_fn`` always prompts; real stdin must be a TTY."""
    if input_fn is not None:
        return True
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _resolve(input_fn: InputFn | None) -> InputFn:
    return input_fn if input_fn is not None else builtins.input


def read_line(prompt: str, *, input_fn: InputFn | None = None) -> str | None:
    """One line of input, or ``None`` when the user sends EOF / Ctrl+C."""
    try:
        return _resolve(input_fn)(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _read_or_cancel(prompt: str, input_fn: InputFn | None) -> str | None:
    """One line, ``None`` on EOF; Ctrl+C raises :class:`OperationCancelledError`."""
    try:
        return _resolve(input_fn)(prompt)
    except EOFError:
        print()
        return None
    except KeyboardInterrupt as exc:
        print()
        raise OperationCancelledError(prompt.strip()) from exc


def ask_yes_no(prompt: str, *, input_fn: InputFn | None = None) -> bool:
    """Ask until y/n. Empty answer and EOF count as yes; Ctrl+C cancels."""
    while True:
        raw = _read_or_cancel(prompt, input_fn)
        if raw is None:
            return True
        try:
            return parse_yes_no(raw)
        except ValueError:
            print("Please answer y or n.")


def wait_for_edit(message: str, *, input_fn: InputFn | None = None) -> bool:
    """Show ``message`` then block until Enter.

    Returns False on EOF (no more input will come); Ctrl+C cancels.
    """
    print(message)
    return _read_or_cancel("", input_fn) is not None


def prompt_choice(
    items: Sequence[Item],
    *,
    parse: Callable[[Sequence[Item], str], T],
    error_cls: type[MathGraderError],
    on_selected: Callable[[T], None],
    prompt: str = "Pilihan: ",
    input_fn: InputFn | None = None,
) -> T:
    """Ask until ``parse(items, raw)`` succeeds; EOF raises ``error_cls``.

    Ctrl+C cancels the whole session (``OperationCancelledError``), matching
    the other prompts in this module.
    """
    while True:
        try:
            raw = _resolve(input_fn)(prompt)
        except EOFError as exc:
            raise error_cls("no input received") from exc
        except KeyboardInterrupt as exc:
            print()
            raise OperationCancelledError(prompt.strip()) from exc
        try:
            selected = parse(items, raw)
        except ValueError as exc:
            print_error(error_cls(str(exc)))
            continue
        on_selected(selected)
        return selected
