"""Ink crop proposal / recrop result schemas."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.models.recognition import DetectedRegion


class PageCropSummary(BaseModel):
    page_number: int = Field(ge=1)
    json_path: Path
    crop_paths: list[Path] = Field(default_factory=list)


class CropProposeResult(BaseModel):
    pages: list[PageCropSummary] = Field(default_factory=list)


class PageRegions(BaseModel):
    """One rendered page with its editable boxes (pixel coordinates of ``image``)."""

    page_number: int = Field(ge=1)
    image: str
    width: int
    height: int
    source: str = ""
    regions: list[DetectedRegion] = Field(default_factory=list)
