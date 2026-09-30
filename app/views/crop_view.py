"""Interactive crop confirmation prompts (CLI view)."""

from __future__ import annotations

from pathlib import Path

from app.models.crop import PageCropSummary
from app.views.prompt_view import InputFn, ask_yes_no, wait_for_edit


def print_crop_summary(summary: PageCropSummary) -> None:
    print(f"Page {summary.page_number}: {len(summary.crop_paths)} crop(s)")
    print(f"  regions JSON: {summary.json_path}")
    for path in summary.crop_paths:
        print(f"  - {path}")


def print_crops_ready(crops_dir: Path) -> None:
    print(f"Crops ready under {crops_dir}")


def print_recrop_result(*, page_count: int, crops_dir: Path) -> None:
    print(f"Recropped {page_count} page(s) under {crops_dir}")


def ask_crops_ok(*, input_fn: InputFn | None = None) -> bool:
    """Return True if user accepts crops. Empty / y / yes → True."""
    return ask_yes_no("Crop OK? [y/n]: ", input_fn=input_fn)


def wait_for_json_edit(*, json_hint: str, input_fn: InputFn | None = None) -> None:
    wait_for_edit(
        "Edit the region boxes in the JSON (x, y, width, height), save the file,"
        f"\nthen press Enter to recrop.\n  {json_hint}",
        input_fn=input_fn,
    )
