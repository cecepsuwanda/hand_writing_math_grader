import sys

from app.views.style import bold, box, red


def print_error(exc: BaseException) -> None:
    message = str(exc)
    lines = [bold("Error"), message]
    print(red(box(lines)), file=sys.stderr)
