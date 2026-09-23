"""Lightweight ANSI styling for CLI views (no third-party deps)."""

from __future__ import annotations

import sys
from typing import Sequence

_VT_ENABLED = False


def _stdout_is_tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def enable_ansi() -> bool:
    """Enable ANSI on Windows consoles when possible. Returns whether color is active."""
    global _VT_ENABLED
    if not _stdout_is_tty():
        return False
    if sys.platform != "win32":
        _VT_ENABLED = True
        return True
    if _VT_ENABLED:
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return False
        enable_flag = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if kernel32.SetConsoleMode(handle, mode.value | enable_flag) == 0:
            return False
        _VT_ENABLED = True
        return True
    except Exception:  # noqa: BLE001 — styling must never break CLI
        return False


def colors_enabled() -> bool:
    return _stdout_is_tty() and (sys.platform != "win32" or _VT_ENABLED or enable_ansi())


def _wrap(code: str, text: str) -> str:
    if not colors_enabled():
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return _wrap("1", text)


def dim(text: str) -> str:
    return _wrap("2", text)


def green(text: str) -> str:
    return _wrap("32", text)


def red(text: str) -> str:
    return _wrap("31", text)


def yellow(text: str) -> str:
    return _wrap("33", text)


def cyan(text: str) -> str:
    return _wrap("36", text)


def rule(title: str = "", width: int = 42) -> str:
    if not title:
        return dim("─" * width)
    label = f" {title} "
    inner = max(width - len(label), 4)
    left = inner // 2
    right = inner - left
    return dim("─" * left) + bold(label) + dim("─" * right)


def box(lines: Sequence[str], *, width: int | None = None) -> str:
    content = [str(line) for line in lines]
    if width is None:
        width = max((len(line) for line in content), default=0)
    width = max(width, 0)
    top = "┌" + "─" * (width + 2) + "┐"
    bottom = "└" + "─" * (width + 2) + "┘"
    body = [f"│ {line.ljust(width)} │" for line in content]
    return "\n".join([top, *body, bottom])


def banner(app_name: str = "Handwriting Math Grader") -> str:
    enable_ansi()
    lines = [
        bold(app_name),
        dim("CLI · Ollama · SymPy"),
    ]
    return cyan(box(lines))
