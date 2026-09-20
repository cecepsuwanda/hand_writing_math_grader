from pathlib import Path

from pydantic import BaseModel, Field


class Page(BaseModel):
    page_number: int
    image: str
    width: int
    height: int


class RenderResult(BaseModel):
    pages: list[Page]
    output_dir: Path
    metadata_path: Path = Field(description="Path to pages.json")
