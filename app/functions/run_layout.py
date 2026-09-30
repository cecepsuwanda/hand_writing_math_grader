"""Per-PDF output layout: ``<output_root>/<run_name>/{pages,crops,recognition,questions}``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PAGES_SUBDIR = "pages"
CROPS_SUBDIR = "crops"
RECOGNITION_SUBDIR = "recognition"
QUESTIONS_SUBDIR = "questions"
RUN_SUBDIRS: tuple[str, ...] = (
    PAGES_SUBDIR,
    CROPS_SUBDIR,
    RECOGNITION_SUBDIR,
    QUESTIONS_SUBDIR,
)

STANDARDS_DIRNAME = "standards"
FALLBACK_RUN_NAME = "run"
RESERVED_SUFFIX = "_run"

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


@dataclass(frozen=True)
class RunLayout:
    """Artifact directories for one processed PDF."""

    root: Path

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def pages_dir(self) -> Path:
        return self.root / PAGES_SUBDIR

    @property
    def crops_dir(self) -> Path:
        return self.root / CROPS_SUBDIR

    @property
    def recognition_dir(self) -> Path:
        return self.root / RECOGNITION_SUBDIR

    @property
    def questions_dir(self) -> Path:
        return self.root / QUESTIONS_SUBDIR

    @property
    def report_dir(self) -> Path:
        return self.root


def sanitize_run_name(raw: str) -> str:
    """Make ``raw`` a safe single folder name (Windows-safe, spaces kept)."""
    name = _ILLEGAL_CHARS.sub("_", raw).strip().rstrip(". ")
    if not name:
        return FALLBACK_RUN_NAME
    lowered = name.lower()
    base = lowered.split(".", 1)[0]
    if lowered == STANDARDS_DIRNAME or base in _WINDOWS_RESERVED:
        return f"{name}{RESERVED_SUFFIX}"
    return name


def safe_run_name(pdf: Path) -> str:
    """Folder name for ``pdf``: its stem with illegal characters replaced."""
    return sanitize_run_name(Path(pdf).stem)


def resolve_run_name(raw: str) -> str:
    """Accept a run folder name or a PDF filename/path; return the run name."""
    value = raw.strip()
    path = Path(value)
    if path.suffix.lower() == ".pdf":
        return safe_run_name(path)
    return sanitize_run_name(path.name if path.name else value)


def build_run_layout(output_root: Path, run_name: str) -> RunLayout:
    return RunLayout(root=Path(output_root) / run_name)


def layout_for_pdf(output_root: Path, pdf: Path) -> RunLayout:
    return build_run_layout(output_root, safe_run_name(pdf))


def list_run_dirs(output_root: Path) -> list[Path]:
    """Run folders under ``output_root`` (skips ``standards`` and flat legacy dirs)."""
    output_root = Path(output_root)
    if not output_root.is_dir():
        return []
    runs = [
        child
        for child in output_root.iterdir()
        if child.is_dir()
        and child.name.lower() != STANDARDS_DIRNAME
        and any((child / sub).is_dir() for sub in RUN_SUBDIRS)
    ]
    return sorted(runs, key=lambda p: p.name.lower())
