"""Factory helpers to wire vision recognizer from AppConfig (DRY for CLI/API)."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.functions.ink_layout import InkLayoutParams
from app.functions.kunci_ingest import load_exam_schema, load_question_stems_from_kunci
from app.interfaces.llm_client import LlmClient
from app.models.exam_schema import ExamSchema
from app.services.vision.ink_region_proposer import InkRegionProposer
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.recognizer import OllamaVisionRecognizer


def ink_params_from_config(config: AppConfig) -> InkLayoutParams:
    ink = config.recognition.ink
    return InkLayoutParams(
        threshold=ink.threshold,
        merge_gap_ratio=ink.merge_gap_ratio,
        min_block_height_ratio=ink.min_block_height_ratio,
        min_row_ink_ratio=ink.min_row_ink_ratio,
        header_fraction=ink.header_fraction,
        column_valley_ratio=ink.column_valley_ratio,
        margin_ratio=ink.margin_ratio,
    )


def build_vision_recognizer(
    config: AppConfig,
    recognition_dir: Path,
    *,
    client: LlmClient | None = None,
    exam_schema: ExamSchema | None = None,
    load_schema_from_standard: bool = True,
) -> OllamaVisionRecognizer:
    """Build ``OllamaVisionRecognizer`` with ink proposer + optional exam schema."""
    ollama = client or OllamaClient(
        base_url=config.ollama.base_url,
        timeout_seconds=config.ollama.timeout_seconds,
        max_retries=config.ollama.max_retries,
    )
    schema = exam_schema
    if schema is None and load_schema_from_standard:
        schema = load_exam_schema(config.grading.standard_dir)
    expected = (
        None
        if schema is not None
        else load_question_stems_from_kunci(config.input.kunci_jawaban_dir)
    )
    return OllamaVisionRecognizer(
        client=ollama,
        model=config.ollama.vision_model,
        output_dir=recognition_dir,
        crops_dir=config.recognition.crops_dir,
        proposer=InkRegionProposer(ink_params_from_config(config)),
        exam_schema=schema,
        expected_questions=expected,
    )
