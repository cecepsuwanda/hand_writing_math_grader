import sys


def print_error(exc: BaseException) -> None:
    print(f"Error: {exc}", file=sys.stderr)
