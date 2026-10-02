"""Vision pass that reads which question labels start in each crop (no transcription)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.functions.json_extract import extract_json_object
from app.functions.kunci_ingest import format_recognition_question_block
from app.interfaces.llm_client import LlmClient
from app.models.exam_schema import ExamSchema

logger = logging.getLogger(__name__)

CROP_LABEL_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "crop_label.txt"


class OllamaQuestionLabeler:
    def __init__(
        self,
        *,
        client: LlmClient,
        model: str,
        exam_schema: ExamSchema | None,
    ) -> None:
        self._client = client
        self._model = model.strip()
        self._numbers = (
            {q.number for q in exam_schema.questions} if exam_schema is not None else set()
        )
        self._prompt = CROP_LABEL_PROMPT.read_text(encoding="utf-8").replace(
            "{{expected_questions}}", format_recognition_question_block(exam_schema)
        )

    def detect(self, crop_path: Path) -> list[int] | None:
        """Question numbers whose label starts in ``crop_path``; ``[]`` if none.

        ``None`` when the model reply is unreadable (no JSON / no number list).
        """
        raw = self._client.generate_with_image(self._prompt, Path(crop_path), self._model)
        try:
            payload = extract_json_object(raw)
        except ValueError as exc:
            logger.warning("crop_label JSON parse failed for %s: %s", crop_path, exc)
            return None
        values = payload.get("question_numbers")
        if not isinstance(values, list):
            logger.warning("crop_label reply for %s has no question_numbers list", crop_path)
            return None
        numbers: list[int] = []
        for value in values:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if self._numbers and number not in self._numbers:
                continue
            if number not in numbers:
                numbers.append(number)
        return numbers
