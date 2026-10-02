"""Error and warning output (always stderr so stdout stays machine-friendly)."""

import sys

from app.views.style import bold, box, for_stream, red, yellow


def print_error(exc: BaseException) -> None:
    message_lines = str(exc).splitlines() or [""]
    lines = [bold("Error"), *message_lines]
    print(for_stream(red(box(lines)), sys.stderr), file=sys.stderr)


def print_warning(message: str) -> None:
    print(for_stream(yellow(message), sys.stderr), file=sys.stderr)
