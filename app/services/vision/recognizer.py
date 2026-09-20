"""Vision recognition service backed by Ollama."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import (
    InvalidRecognitionJsonError,
    OllamaModelNotConfiguredError,
)
from app.functions.json_extract import extract_json_object
from app.functions.page_names import page_recognition_filename
from app.interfaces.recognizer import VisionRecognizer
from app.models.recognition import PageRecognition
from app.services.vision.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "recognition.txt"
PROMPT_VERSION = "recognition-v1"


class OllamaVisionRecognizer(VisionRecognizer):
    def __init__(
        self,
        client: OllamaClient,
        model: str,
        output_dir: Path,
        prompt_path: Path | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._client = client
        self._model = model.strip()
        self._output_dir = Path(output_dir)
        self._prompt_path = Path(prompt_path) if prompt_path else DEFAULT_PROMPT_PATH
        self._prompt_version = prompt_version
        self._prompt = self._load_prompt()

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def recognize_page(self, image_path: Path, page_number: int) -> PageRecognition:
        if not self._model:
            raise OllamaModelNotConfiguredError()

        image_path = Path(image_path)
        raw = self._client.generate_with_image(self._prompt, image_path, self._model)
        try:
            payload = extract_json_object(raw)
            payload["page_number"] = page_number
            recognition = PageRecognition.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise InvalidRecognitionJsonError(page_number, str(exc)) from exc

        recognition = recognition.model_copy(
            update={
                "page_number": page_number,
                "prompt_version": self._prompt_version,
                "model": self._model,
            }
        )
        self._write_artifact(recognition)
        logger.info(
            "recognized page=%s questions=%s model=%s",
            page_number,
            len(recognition.questions),
            self._model,
        )
        return recognition

    def _load_prompt(self) -> str:
        return self._prompt_path.read_text(encoding="utf-8")

    def _write_artifact(self, recognition: PageRecognition) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / page_recognition_filename(recognition.page_number)
        path.write_text(
            recognition.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path
