"""Compile report.tex → report.pdf with pdflatex (the only subprocess in the app)."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

from app.exceptions import ReportPdfError
from app.functions.latex_compile import (
    LATEX_JUNK_SUFFIXES,
    build_jobname,
    latex_error_summary,
    pdflatex_command,
)
from app.interfaces.latex_compiler import LatexCompiler

logger = logging.getLogger(__name__)

Runner = Callable[..., subprocess.CompletedProcess]

_PDFLATEX = "pdflatex"
_MIKTEX_BIN = Path("MiKTeX") / "miktex" / "bin" / "x64" / "pdflatex.exe"
_TEXLIVE_ROOT = Path("C:/texlive")


def _standard_locations() -> Iterator[Path]:
    for env_name, prefix in (
        ("ProgramFiles", Path()),
        ("LOCALAPPDATA", Path("Programs")),
        ("ProgramFiles(x86)", Path()),
    ):
        root = os.environ.get(env_name)
        if root:
            yield Path(root) / prefix / _MIKTEX_BIN
    if _TEXLIVE_ROOT.is_dir():
        yield from sorted(_TEXLIVE_ROOT.glob("*/bin/win*/pdflatex.exe"), reverse=True)


def resolve_pdflatex(configured: str = "") -> Path | None:
    """Configured path/command, else ``pdflatex`` on PATH, else a standard install."""
    wanted = configured.strip()
    if wanted:
        if Path(wanted).is_file():
            return Path(wanted)
        found = shutil.which(wanted)
        return Path(found) if found else None
    found = shutil.which(_PDFLATEX)
    if found:
        return Path(found)
    return next((path for path in _standard_locations() if path.is_file()), None)


class PdfLatexCompiler(LatexCompiler):
    def __init__(
        self,
        executable: Path | None,
        *,
        passes: int = 2,
        timeout_seconds: float = 120.0,
        runner: Runner = subprocess.run,
    ) -> None:
        self._executable = executable
        self._passes = passes
        self._timeout = timeout_seconds
        self._runner = runner

    def compile(self, tex_path: Path) -> Path:
        if self._executable is None:
            raise ReportPdfError(
                "pdflatex tidak ditemukan; isi report.pdf.pdflatex_path di config.yaml "
                "atau env PDFLATEX_PATH"
            )
        tex_path = Path(tex_path)
        folder, stem = tex_path.parent, tex_path.stem
        jobname = build_jobname(stem)
        try:
            self._run_passes(pdflatex_command(self._executable, tex_path.name, jobname), folder, jobname)
            pdf_path = self._publish_pdf(folder, jobname, stem)
        finally:
            self._keep_log(folder, jobname, stem)
            self._remove_junk(folder, jobname, stem)
        logger.info("Compiled %s", pdf_path)
        return pdf_path

    def _run_passes(self, command: list[str], folder: Path, jobname: str) -> None:
        for _ in range(self._passes):
            try:
                completed = self._runner(
                    command,
                    cwd=folder,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self._timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ReportPdfError(f"pdflatex melebihi {self._timeout:g} detik") from exc
            except OSError as exc:
                raise ReportPdfError(f"pdflatex gagal dijalankan: {exc}") from exc
            if completed.returncode != 0:
                log_path = folder / f"{jobname}.log"
                log_text = (
                    log_path.read_text(encoding="latin-1") if log_path.is_file() else ""
                )
                summary = latex_error_summary(log_text)
                raise ReportPdfError(
                    f"pdflatex error: {summary}" if summary
                    else f"pdflatex keluar dengan kode {completed.returncode}"
                )

    @staticmethod
    def _publish_pdf(folder: Path, jobname: str, stem: str) -> Path:
        built = folder / f"{jobname}.pdf"
        if not built.is_file():
            raise ReportPdfError("pdflatex tidak menghasilkan PDF")
        target = folder / f"{stem}.pdf"
        try:
            os.replace(built, target)
        except PermissionError as exc:
            raise ReportPdfError(
                f"{target.name} sedang dibuka program lain; tutup lalu kompilasi ulang"
            ) from exc
        return target

    @staticmethod
    def _keep_log(folder: Path, jobname: str, stem: str) -> None:
        log_path = folder / f"{jobname}.log"
        if log_path.is_file():
            with contextlib.suppress(OSError):
                os.replace(log_path, folder / f"{stem}.log")

    @staticmethod
    def _remove_junk(folder: Path, jobname: str, stem: str) -> None:
        leftovers = [p for p in folder.iterdir() if p.name.startswith(f"{jobname}.")]
        leftovers += [folder / f"{stem}{suffix}" for suffix in LATEX_JUNK_SUFFIXES]
        for path in leftovers:
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)
