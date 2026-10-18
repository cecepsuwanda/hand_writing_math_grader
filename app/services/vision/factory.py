"""Factory helpers to wire vision recognizer from AppConfig (DRY for the web pipeline)."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.exceptions import UnknownTopicError
from app.functions.ink_layout import InkLayoutParams
from app.functions.kunci_ingest import load_exam_schema, load_question_stems_from_kunci
from app.services.standards.standard_dir import resolve_standard_dir
from app.services.vision.ink_region_proposer import InkRegionProposer
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.recognizer import OllamaVisionRecognizer
from app.topics.registry import get_pack, resolve_pack
from app.topics.runtime import get_active_pack


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
        long_line_ratio=ink.long_line_ratio,
        paper_offset=ink.paper_offset,
    )


def build_vision_recognizer(
    config: AppConfig,
    recognition_dir: Path,
    *,
    crops_dir: Path | None = None,
    standard_dir: Path | None = None,
    topic_id: str | None = None,
) -> OllamaVisionRecognizer:
    """Build ``OllamaVisionRecognizer`` with ink proposer + optional exam schema.

    The schema comes only from ``standard_dir`` (default: the topic's
    ``topik_<bab>`` folder), so an overridden standards folder never silently
    falls back to the default one.
    """
    ollama = OllamaClient(
        base_url=config.ollama.base_url,
        timeout_seconds=config.ollama.timeout_seconds,
        max_retries=config.ollama.max_retries,
    )
    standard = resolve_standard_dir(config, topic_id=topic_id, standard_dir=standard_dir)
    schema = load_exam_schema(standard)
    expected = (
        None
        if schema is not None
        else load_question_stems_from_kunci(
            config.input.kunci_jawaban_dir,
            topic_id=(topic_id or "").strip() or config.grading.topic_id,
        )
    )
    pack = get_active_pack()
    if pack is None:
        try:
            pack = (
                get_pack(topic_id)
                if (topic_id or "").strip()
                else resolve_pack()
            )
        except UnknownTopicError:
            pack = None
    role_instructions = (
        (getattr(pack, "recognition_role_instructions", "") or "")
        if pack is not None
        else ""
    )
    return OllamaVisionRecognizer(
        client=ollama,
        model=config.ollama.vision_model,
        output_dir=recognition_dir,
        crops_dir=crops_dir,
        proposer=InkRegionProposer(ink_params_from_config(config)),
        exam_schema=schema,
        expected_questions=expected,
        pack_role_instructions=role_instructions,
    )
