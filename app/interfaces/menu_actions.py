"""Port for the side-effecting steps behind each interactive main-menu entry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.config import AppConfig
from app.functions.run_layout import RunLayout
from app.models.question_crops import LabelMode


@runtime_checkable
class MenuActions(Protocol):
    def select_topic(self, active_topic_id: str) -> str:
        """Ask for a topic pack; return its id (``active_topic_id`` if cancelled)."""

    def select_pdf(self, config: AppConfig) -> Path:
        """Ask for a student PDF under ``config.input.jawaban_dir``."""

    def pick_run(self, config: AppConfig) -> RunLayout:
        """Resolve an existing run folder (single run, or interactive choice)."""

    def ingest(self, config: AppConfig, topic_id: str) -> None:
        """Ask for a kunci ``.tex`` and ingest it into the standards dir."""

    def propose_crops(self, config: AppConfig, layout: RunLayout, pdf_path: Path) -> None:
        """Render ``pdf_path``, ink-propose crops, and confirm them."""

    def recrop(self, config: AppConfig, layout: RunLayout) -> None:
        """Recrop from edited regions JSON, then confirm."""

    def label(self, config: AppConfig, layout: RunLayout, mode: LabelMode) -> None:
        """Label (or reload) question numbers per crop, then confirm."""

    def finish(self, config: AppConfig, layout: RunLayout, topic_id: str | None) -> None:
        """Run recognize → report from the confirmed crops."""
