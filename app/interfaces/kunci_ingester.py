"""Port for ingesting kunci jawaban TeX into a standards directory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class KunciIngestPort(Protocol):
    @property
    def standard_dir(self) -> Path:
        """Standards directory this ingester writes to."""

    def ingest_file(self, kunci_path: Path) -> list[Path]:
        """Ingest one kunci ``.tex`` file; return written artifact paths."""

    def ingest_dir(self, kunci_dir: Path) -> list[Path]:
        """Ingest every kunci ``.tex`` in a folder; return written artifact paths."""
