from abc import ABC, abstractmethod
from pathlib import Path

from app.models.recognition import PageRecognition


class VisionRecognizer(ABC):
    @abstractmethod
    def recognize_page(self, image_path: Path, page_number: int) -> PageRecognition:
        """Recognize handwritten math content on a single page image."""

    @abstractmethod
    def recognize_page_from_crops(
        self, image_path: Path, page_number: int
    ) -> PageRecognition:
        """Recognize from approved crop PNGs / regions JSON (no re-propose)."""
