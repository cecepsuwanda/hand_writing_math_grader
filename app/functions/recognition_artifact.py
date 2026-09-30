"""Presence checks for per-page recognition JSON artifacts."""

from __future__ import annotations

from pathlib import Path

PAGE_RECOGNITION_GLOB = "page_*_recognition.json"


def has_recognition_artifacts(recognition_dir: Path) -> bool:
    recognition_dir = Path(recognition_dir)
    return recognition_dir.is_dir() and any(recognition_dir.glob(PAGE_RECOGNITION_GLOB))
