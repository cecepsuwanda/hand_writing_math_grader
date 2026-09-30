"""Detect source artifacts that change while a stage writes its own outputs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path


def snapshot_files(paths: Iterable[Path]) -> dict[Path, bytes]:
    return {Path(path): Path(path).read_bytes() for path in paths}


def changed_files(snapshot: Mapping[Path, bytes]) -> list[Path]:
    """Paths whose current bytes differ from ``snapshot`` (missing counts as changed)."""
    return [
        path
        for path, original in snapshot.items()
        if not path.is_file() or path.read_bytes() != original
    ]
