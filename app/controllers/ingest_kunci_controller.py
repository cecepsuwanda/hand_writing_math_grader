"""Orchestrate kunci_jawaban TeX → standards/solutions ingest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.standards.kunci_ingester import KunciIngester


@dataclass(frozen=True)
class IngestKunciResult:
    written: list[Path]
    standard_dir: Path
    source: Path


class IngestKunciController:
    def ingest(
        self,
        *,
        kunci_path: Path | None,
        kunci_dir: Path,
        standard_dir: Path,
    ) -> IngestKunciResult:
        ingester = KunciIngester(standard_dir)
        if kunci_path is not None:
            source = Path(kunci_path)
            written = ingester.ingest_file(source)
        else:
            source = Path(kunci_dir)
            written = ingester.ingest_dir(source)
        return IngestKunciResult(
            written=written,
            standard_dir=Path(standard_dir),
            source=source,
        )
