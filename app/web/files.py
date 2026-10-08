"""Map URL segments and uploads onto files under the configured folders.

Every path built from request input goes through here, so a crafted run name,
crop name, or upload filename can never reach outside its folder.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path, PureWindowsPath

from app.exceptions import (
    ArtifactNotFoundError,
    KunciNotFoundError,
    PdfNotFoundError,
    RunNotFoundError,
    UnsafeArtifactPathError,
    UploadRejectedError,
)
from app.functions.page_names import page_image_filename
from app.functions.question_names import (
    report_html_filename,
    report_json_filename,
    report_tex_filename,
    summary_csv_filename,
)
from app.functions.run_layout import RunLayout, list_run_dirs

_CROP_NAME_RE = re.compile(r"^page_(\d{3})_region_\d{2}_solution\.png$")
_PDF_MAGIC = b"%PDF"
_BYTES_PER_MB = 1024 * 1024


class ReportFile(StrEnum):
    PDF = "pdf"
    TEX = "tex"
    HTML = "html"
    JSON = "json"
    CSV = "csv"


_REPORT_FILENAMES: dict[ReportFile, str] = {
    ReportFile.PDF: "report.pdf",
    ReportFile.TEX: report_tex_filename(),
    ReportFile.HTML: report_html_filename(),
    ReportFile.JSON: report_json_filename(),
    ReportFile.CSV: summary_csv_filename(),
}


def require_run(output_root: Path, run_name: str) -> RunLayout:
    """Layout of an existing run folder, matched by exact name (never joined blindly)."""
    wanted = run_name.strip()
    for run_dir in list_run_dirs(output_root):
        if run_dir.name == wanted:
            return RunLayout(root=run_dir)
    raise RunNotFoundError(wanted)


def page_image_path(layout: RunLayout, page_number: int) -> Path:
    try:
        path = layout.pages_dir / page_image_filename(page_number)
    except ValueError as exc:
        raise UnsafeArtifactPathError(str(page_number)) from exc
    if not path.is_file():
        raise ArtifactNotFoundError(f"gambar halaman {page_number} di run {layout.name}")
    return path


def crop_image_path(layout: RunLayout, crop_name: str) -> Path:
    """``page_NNN_region_MM_solution.png`` under its own page folder."""
    name = Path(crop_name).name
    match = _CROP_NAME_RE.match(name)
    if match is None or name != crop_name:
        raise UnsafeArtifactPathError(crop_name)
    path = layout.crops_dir / f"page_{match.group(1)}" / name
    if not path.is_file():
        raise ArtifactNotFoundError(f"crop {name} di run {layout.name}")
    return path


def report_file_path(layout: RunLayout, kind: ReportFile) -> Path:
    path = layout.report_dir / _REPORT_FILENAMES[kind]
    if not path.is_file():
        raise ArtifactNotFoundError(f"{path.name} di run {layout.name}")
    return path


def existing_report_files(layout: RunLayout) -> list[ReportFile]:
    return [kind for kind, name in _REPORT_FILENAMES.items() if (layout.report_dir / name).is_file()]


def require_input_file(folder: Path, name: str, *, suffix: str) -> Path:
    """A file directly inside ``folder`` (``.pdf`` jawaban / ``.tex`` kunci) by its bare name."""
    bare = _bare_name(name)
    path = Path(folder) / bare
    if bare != name.strip() or path.suffix.lower() != suffix or not path.is_file():
        if suffix == ".pdf":
            raise PdfNotFoundError(path)
        raise KunciNotFoundError(path)
    return path


def save_upload(
    folder: Path, filename: str, data: bytes, *, suffix: str, max_mb: int
) -> Path:
    """Store an uploaded ``.pdf`` / ``.tex`` in ``folder`` under its bare name (overwrites)."""
    bare = _bare_name(filename)
    if not bare or bare.startswith(".") or Path(bare).suffix.lower() != suffix:
        raise UploadRejectedError(filename or "(tanpa nama)", f"harus file {suffix}")
    if not data:
        raise UploadRejectedError(bare, "file kosong")
    if len(data) > max_mb * _BYTES_PER_MB:
        raise UploadRejectedError(bare, f"lebih dari {max_mb} MB")
    if suffix == ".pdf" and not data.startswith(_PDF_MAGIC):
        raise UploadRejectedError(bare, "bukan PDF")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / bare
    path.write_bytes(data)
    return path


def _bare_name(raw: str) -> str:
    """Last path component for both ``/`` and ``\\`` separators (browsers send either)."""
    return PureWindowsPath(raw.strip()).name
