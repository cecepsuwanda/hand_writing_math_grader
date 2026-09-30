"""Orchestrate kunci_jawaban TeX → standards/solutions ingest."""

from __future__ import annotations

from pathlib import Path

from app.exceptions import StandardDirMismatchError
from app.functions.standard_extract import exam_schema_path
from app.interfaces.kunci_ingester import KunciIngestPort
from app.models.standards import IngestKunciResult


class IngestKunciController:
    def __init__(self, ingester: KunciIngestPort) -> None:
        self._ingester = ingester

    def ingest(
        self,
        *,
        kunci_path: Path | None,
        kunci_dir: Path,
        standard_dir: Path,
    ) -> IngestKunciResult:
        resolved = Path(standard_dir).resolve()
        ingester_dir = self._ingester.standard_dir.resolve()
        if resolved != ingester_dir:
            raise StandardDirMismatchError(resolved, ingester_dir)
        if kunci_path is not None:
            source = Path(kunci_path)
            written = self._ingester.ingest_file(source)
        else:
            source = Path(kunci_dir)
            written = self._ingester.ingest_dir(source)
        write_dir = self._ingester.standard_dir
        schema = exam_schema_path(write_dir)
        return IngestKunciResult(
            written=written,
            standard_dir=write_dir,
            source=source,
            schema_path=schema if written and schema.is_file() else None,
        )
