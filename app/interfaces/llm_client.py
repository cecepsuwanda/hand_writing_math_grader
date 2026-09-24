"""Port for text / vision LLM generation (Ollama or doubles)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmClient(Protocol):
    """Narrow chat API used by vision recognition and reasoning judges."""

    def generate(self, prompt: str, model: str) -> str:
        """Chat completion without an image."""

    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        """Chat completion with a single image attachment."""
