"""Pure helpers for running pdflatex on report.tex."""

from __future__ import annotations

from pathlib import Path

LATEX_JUNK_SUFFIXES: tuple[str, ...] = (
    ".aux",
    ".out",
    ".toc",
    ".lof",
    ".lot",
    ".fls",
    ".synctex.gz",
)

_LINE_MARK = "l."


def build_jobname(stem: str) -> str:
    """Scratch job name so a viewer holding ``<stem>.pdf`` never blocks pdflatex."""
    return f"{stem}_build"


def pdflatex_command(executable: Path | str, tex_name: str, jobname: str) -> list[str]:
    return [
        str(executable),
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={jobname}",
        tex_name,
    ]


def latex_error_summary(log_text: str) -> str | None:
    """First ``! ...`` error of a pdflatex log, with its ``l.NN`` location when present."""
    lines = log_text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("!"):
            continue
        message = line.lstrip("! ").strip()
        location = next(
            (
                candidate.strip()
                for candidate in lines[index + 1 : index + 8]
                if candidate.startswith(_LINE_MARK)
            ),
            "",
        )
        return f"{message} ({location})" if location else message
    return None
