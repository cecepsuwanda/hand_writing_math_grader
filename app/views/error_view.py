"""Error and warning output (always stderr so stdout stays machine-friendly)."""

import sys

from app.views.style import bold, box, red, yellow


def print_error(exc: BaseException) -> None:
    message_lines = str(exc).splitlines() or [""]
    lines = [bold("Error"), *message_lines]
    print(red(box(lines)), file=sys.stderr)


def print_warning(message: str) -> None:
    print(yellow(message), file=sys.stderr)
