"""Load application configuration from YAML and environment variables."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.exceptions import (
    ConfigInvalidError,
    ConfigNotFoundError,
    OllamaModelNotConfiguredError,
)
from app.models.defaults import DEFAULT_TOPIC_ID

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

logger = logging.getLogger(__name__)


class PdfConfig(BaseModel):
    dpi: int = 200


class OutputConfig(BaseModel):
    # Each processed PDF gets <root_dir>/<pdf stem>/{pages,crops,recognition,questions}.
    root_dir: Path = Path("data/output")


class InputConfig(BaseModel):
    jawaban_dir: Path = Path("data/input/jawaban")
    # Source for kunci ingest → standards/solutions (enumerate+align+HP slice).
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
    min_row_ink_ratio: float = 0.002
    header_fraction: float = 0.08
    column_valley_ratio: float = 0.15
    margin_ratio: float = 0.02
    long_line_ratio: float = 0.1
    paper_offset: int = 40


class RecognitionConfig(BaseModel):
    ink: InkLayoutConfig = Field(default_factory=InkLayoutConfig)
    review_min_confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class GradingConfig(BaseModel):
    # Each topic pack ingests into <standards_root>/topik_<bab> (e.g. 1.5 → topik_1).
    standards_root: Path = Path("data/output/standards")
    topic_id: str = DEFAULT_TOPIC_ID
    # LLM fallback verdicts below this confidence (or without one) go to human review.
    llm_min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ReportPdfConfig(BaseModel):
    enabled: bool = True
    # Empty = auto-detect (PATH, then standard MiKTeX / TeX Live locations).
    pdflatex_path: str = ""
    passes: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=120.0, gt=0)


class ReportConfig(BaseModel):
    pdf: ReportPdfConfig = Field(default_factory=ReportPdfConfig)


class WebConfig(BaseModel):
    # Student answers stay on this machine: bind to loopback unless deliberately changed.
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    max_upload_mb: int = Field(default=50, ge=1)


class AppConfig(BaseModel):
    pdf: PdfConfig = Field(default_factory=PdfConfig)
    input: InputConfig = Field(default_factory=InputConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    recognition: RecognitionConfig = Field(default_factory=RecognitionConfig)
    grading: GradingConfig = Field(default_factory=GradingConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    web: WebConfig = Field(default_factory=WebConfig)


def require_vision_model(config: AppConfig) -> None:
    """Raise before any stage that sends images to Ollama."""
    if not config.ollama.vision_model.strip():
        raise OllamaModelNotConfiguredError()


def load_config(path: Path | None = None) -> AppConfig:
    """YAML + env overrides. A missing default file means built-in defaults;
    a missing explicitly requested file is an error (likely a typo in ``--config``)."""
    config_path = DEFAULT_CONFIG_PATH if path is None else Path(path)
    explicit = path is not None and config_path.resolve() != DEFAULT_CONFIG_PATH
    if explicit and not config_path.is_file():
        raise ConfigNotFoundError(config_path)
    raw: dict[str, object] = {}
    if config_path.is_file():
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigInvalidError(str(config_path), f"YAML tidak terbaca: {exc}") from exc
        if loaded and not isinstance(loaded, dict):
            raise ConfigInvalidError(
                str(config_path),
                f"isi teratas harus berupa mapping (key: value), bukan {type(loaded).__name__}",
            )
        if loaded:
            raw = loaded
    _warn_legacy_keys(raw, config_path)
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigInvalidError(str(config_path), _validation_summary(exc)) from exc
    return _apply_env(config)


def _validation_summary(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )


def _env_number(name: str, convert: type[int] | type[float]) -> int | float | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return convert(raw)
    except ValueError as exc:
        raise ConfigInvalidError(
            f"env {name}", f"nilai {raw!r} bukan {convert.__name__}"
        ) from exc


def _warn_legacy_keys(raw: dict[str, object], config_path: Path) -> None:
    grading = raw.get("grading")
    if isinstance(grading, dict) and "standard_dir" in grading:
        logger.warning(
            "%s: grading.standard_dir is ignored; standards now live in "
            "grading.standards_root/topik_<bab> (use --standard to override).",
            config_path,
        )


def _apply_env(config: AppConfig) -> AppConfig:
    ollama = config.ollama.model_copy()
    base_url = os.environ.get("OLLAMA_BASE_URL")
    vision_model = os.environ.get("OLLAMA_VISION_MODEL")
    reasoning_model = os.environ.get("OLLAMA_REASONING_MODEL")
    timeout = _env_number("OLLAMA_TIMEOUT_SECONDS", float)
    retries = _env_number("OLLAMA_MAX_RETRIES", int)
    if base_url:
        ollama.base_url = base_url
    if vision_model:
        ollama.vision_model = vision_model
    if reasoning_model:
        ollama.reasoning_model = reasoning_model
    if timeout is not None:
        ollama.timeout_seconds = float(timeout)
    if retries is not None:
        ollama.max_retries = int(retries)
    return config.model_copy(update={"ollama": ollama, "report": _report_from_env(config.report)})


def _report_from_env(report: ReportConfig) -> ReportConfig:
    pdflatex_path = os.environ.get("PDFLATEX_PATH")
    if not pdflatex_path:
        return report
    pdf = report.pdf.model_copy(update={"pdflatex_path": pdflatex_path})
    return report.model_copy(update={"pdf": pdf})
