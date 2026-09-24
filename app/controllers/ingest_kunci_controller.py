"""Orchestrate kunci_jawaban TeX → standards/solutions ingest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.functions.standard_extract import exam_schema_path
from app.services.standards.kunci_ingester import KunciIngester


@dataclass(frozen=True)
class IngestKunciResult:
    written: list[Path]
    standard_dir: Path
    source: Path
    schema_path: Path | None = None


class IngestKunciController:
    def __init__(self, ingester: KunciIngester) -> None:
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
            raise ValueError(
                f"standard_dir {resolved} does not match injected "
                f"KunciIngester dir {ingester_dir}"
            )
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
            schema_path=schema if schema.is_file() else None,
        )
