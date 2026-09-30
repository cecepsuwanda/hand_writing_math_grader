"""Ink crop proposal / recrop result schemas."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class PageCropSummary(BaseModel):
    page_number: int = Field(ge=1)
    json_path: Path
    crop_paths: list[Path] = Field(default_factory=list)


class CropProposeResult(BaseModel):
    pages: list[PageCropSummary] = Field(default_factory=list)
