"""Port for detecting which exam questions start in a crop image."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class QuestionLabeler(Protocol):
    def detect(self, crop_path: Path) -> list[int] | None:
        """Question numbers whose label starts in the crop (``[]`` = continuation).

        ``None`` = the label could not be read; the crop is treated as a
        continuation but reported so the user can check it.
        """
