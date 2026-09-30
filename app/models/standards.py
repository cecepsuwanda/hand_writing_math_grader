"""Kunci ingest result schema."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class IngestKunciResult(BaseModel):
    written: list[Path] = Field(default_factory=list)
    standard_dir: Path
    source: Path
    schema_path: Path | None = None
