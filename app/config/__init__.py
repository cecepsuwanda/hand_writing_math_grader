"""Load application configuration from YAML and environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


class PdfConfig(BaseModel):
    dpi: int = 200
    output_dir: Path = Path("data/output/pages")


class InputConfig(BaseModel):
    jawaban_dir: Path = Path("data/input/jawaban")
    # Source for CLI ingest-kunci → standards/solutions (enumerate+align+HP slice).
    kunci_jawaban_dir: Path = Path("data/input/kunci_jawaban")


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    vision_model: str = ""
    reasoning_model: str = ""
    timeout_seconds: float = 120.0
    max_retries: int = 2


class InkLayoutConfig(BaseModel):
    threshold: int = 200
    merge_gap_ratio: float = 0.018
    min_block_height_ratio: float = 0.03
    header_fraction: float = 0.08
    column_valley_ratio: float = 0.15
    margin_ratio: float = 0.02


class RecognitionConfig(BaseModel):
    output_dir: Path = Path("data/output/recognition")
    crops_dir: Path = Path("data/output/crops")
    ink: InkLayoutConfig = Field(default_factory=InkLayoutConfig)


class QuestionsConfig(BaseModel):
    output_dir: Path = Path("data/output/questions")


class GradingConfig(BaseModel):
    standard_dir: Path = Path("data/output/standards/exam_001")


class ReportConfig(BaseModel):
    output_dir: Path = Path("data/output")


class AppConfig(BaseModel):
    pdf: PdfConfig = Field(default_factory=PdfConfig)
    input: InputConfig = Field(default_factory=InputConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    recognition: RecognitionConfig = Field(default_factory=RecognitionConfig)
    questions: QuestionsConfig = Field(default_factory=QuestionsConfig)
    grading: GradingConfig = Field(default_factory=GradingConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = DEFAULT_CONFIG_PATH if path is None else Path(path)
    raw: dict[str, object] = {}
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded:
            raw = loaded
    return _apply_env(AppConfig.model_validate(raw))


def _apply_env(config: AppConfig) -> AppConfig:
    ollama = config.ollama.model_copy()
    base_url = os.environ.get("OLLAMA_BASE_URL")
    vision_model = os.environ.get("OLLAMA_VISION_MODEL")
    reasoning_model = os.environ.get("OLLAMA_REASONING_MODEL")
    timeout = os.environ.get("OLLAMA_TIMEOUT_SECONDS")
    retries = os.environ.get("OLLAMA_MAX_RETRIES")
    if base_url:
        ollama.base_url = base_url
    if vision_model:
        ollama.vision_model = vision_model
    if reasoning_model:
        ollama.reasoning_model = reasoning_model
    if timeout:
        ollama.timeout_seconds = float(timeout)
    if retries:
        ollama.max_retries = int(retries)
    return config.model_copy(update={"ollama": ollama})
