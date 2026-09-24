"""Interactive crop confirmation prompts (CLI view)."""

from __future__ import annotations

import sys
from pathlib import Path


def print_crop_summary(
    *,
    page_number: int,
    json_path: Path,
    crop_paths: list[Path],
) -> None:
    print(f"Page {page_number}: {len(crop_paths)} crop(s)")
    print(f"  regions JSON: {json_path}")
    for path in crop_paths:
        print(f"  - {path}")


def ask_crops_ok(*, input_fn=input) -> bool:
    """Return True if user accepts crops. Empty / y / yes → True."""
    raw = input_fn("Crop OK? [y/n]: ").strip().lower()
    if raw in {"", "y", "yes"}:
        return True
    if raw in {"n", "no"}:
        return False
    print("Please answer y or n.")
    return ask_crops_ok(input_fn=input_fn)


def wait_for_json_edit(*, json_hint: str, input_fn=input) -> None:
    print(
        "Edit the region boxes in the JSON (x, y, width, height), save the file,"
        f"\nthen press Enter to recrop.\n  {json_hint}"
    )
    input_fn("")


def should_prompt_interactively(*, force_yes: bool) -> bool:
    """Skip prompts when ``--yes`` or stdin is not a TTY."""
    if force_yes:
        return False
    return bool(getattr(sys.stdin, "isatty", lambda: False)())
