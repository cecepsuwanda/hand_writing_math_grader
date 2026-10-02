"""Presence checks and pruning for per-page recognition JSON artifacts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

PAGE_RECOGNITION_GLOB = "page_*_recognition.json"
_PAGE_RECOGNITION_RE = re.compile(r"^page_(\d+)_recognition\.json$")


def has_recognition_artifacts(recognition_dir: Path) -> bool:
    recognition_dir = Path(recognition_dir)
    return recognition_dir.is_dir() and any(recognition_dir.glob(PAGE_RECOGNITION_GLOB))


def prune_stale_recognition(recognition_dir: Path, keep_pages: Iterable[int]) -> list[str]:
    """Delete ``page_*_recognition.json`` for pages outside ``keep_pages``; other files stay."""
    recognition_dir = Path(recognition_dir)
    if not recognition_dir.is_dir():
        return []
    keep = set(keep_pages)
    removed: list[str] = []
    for path in sorted(recognition_dir.glob(PAGE_RECOGNITION_GLOB)):
        match = _PAGE_RECOGNITION_RE.match(path.name)
        if match is None or int(match.group(1)) in keep:
            continue
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed
