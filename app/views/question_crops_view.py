"""CLI view for the question → crop mapping (summary, confirm, fallback warning)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.functions.question_crops import question_crops_dir
from app.functions.regions_artifact import crop_display_name
from app.models.question_crops import QuestionCropsReport
from app.views.error_view import print_warning
from app.views.prompt_view import InputFn, ask_yes_no, wait_for_edit
from app.views.style import bold, dim, red


def print_question_crops_summary(
    mapping: Mapping[int, list[str]],
    report: QuestionCropsReport,
    *,
    json_dir: Path,
) -> None:
    print(bold(f"Nomor soal per crop ({len(mapping)} soal)"))
    for number in sorted(mapping):
        names = ", ".join(crop_display_name(n) for n in mapping[number]) or "-"
        print(f"  Soal {number}: {names}")
    for error in report.errors:
        print_warning(red(f"  Error: {error}"))
    if report.missing_questions:
        missing = ", ".join(str(n) for n in report.missing_questions)
        print_warning(f"  Peringatan: soal tanpa crop: {missing}")
    if report.unassigned_crops:
        loose = ", ".join(crop_display_name(n) for n in report.unassigned_crops)
        print_warning(f"  Peringatan: crop tanpa soal: {loose}")
    print(dim(f"  JSON: {json_dir}"))
    print()


def ask_question_crops_ok(*, input_fn: InputFn | None = None) -> bool:
    """Return True if user accepts the mapping. Empty / y / yes → True."""
    return ask_yes_no("Nomor soal OK? [y/n]: ", input_fn=input_fn)


def wait_for_question_crops_edit(
    *, json_dir: Path, input_fn: InputFn | None = None
) -> bool:
    """False when input ended (EOF) instead of Enter."""
    return wait_for_edit(
        "Edit daftar \"crops\" di question_*.json (satu crop boleh di beberapa soal),"
        f"\nsimpan, lalu tekan Enter untuk memuat ulang.\n  {json_dir}",
        input_fn=input_fn,
    )


def print_question_crops_missing(crops_dir: Path) -> None:
    print_warning(
        bold("Peringatan: nomor soal belum ditetapkan")
        + f" ({question_crops_dir(crops_dir)} tidak ada)."
    )
    print_warning(
        dim(
            "  Nomor soal ditebak model per crop. Jalankan menu 5 "
            "(label-questions) untuk menetapkannya."
        )
    )
