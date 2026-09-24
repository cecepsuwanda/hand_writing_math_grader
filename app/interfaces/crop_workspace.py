"""Port for ink crop propose / recrop workspace (no VLM)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.recognition import DetectedRegion


class CropWorkspace(ABC):
    """Ink boxes → editable regions JSON → Pillow crop PNGs."""

    @property
    @abstractmethod
    def crops_dir(self) -> Path:
        """Root directory for per-page crop folders."""

    @abstractmethod
    def page_crop_dir(self, page_number: int) -> Path:
        """Directory holding regions JSON and crop PNGs for one page."""

    @abstractmethod
    def propose_page_crops(
        self, image_path: Path, page_number: int
    ) -> tuple[list[DetectedRegion], str, Path]:
        """Propose ink regions, write JSON+PNGs. Returns (regions, source, json_path)."""

    @abstractmethod
    def recrop_page_from_json(
        self, image_path: Path, page_number: int
    ) -> tuple[list[DetectedRegion], str, Path]:
        """Reload editable regions JSON and rewrite crop PNGs."""
