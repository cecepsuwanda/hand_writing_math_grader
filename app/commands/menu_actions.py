"""CLI adapter for the :class:`MenuActions` port used by ``MenuController``."""

from __future__ import annotations

from pathlib import Path

from app.commands import flows
from app.config import AppConfig
from app.functions.run_layout import RunLayout
from app.models.question_crops import LabelMode
from app.services import pipeline_factory

MENU_RUN_HINT = "Pilih menu 3 (crop PDF) dulu untuk membuat folder run."


class CliMenuActions:
    """:class:`MenuActions` backed by the shared CLI flows."""

    def select_topic(self, active_topic_id: str) -> str | None:
        return flows.select_topic_interactive(active_topic_id)

    def select_pdf(self, config: AppConfig) -> Path:
        return flows.select_pdf_interactive(config.input.jawaban_dir)

    def pick_run(self, config: AppConfig) -> RunLayout:
        return flows.pick_existing_run(config.output.root_dir, hint=MENU_RUN_HINT)

    def ingest(self, config: AppConfig, topic_id: str) -> None:
        kunci_dir = config.input.kunci_jawaban_dir
        flows.ingest(
            config,
            kunci_path=flows.select_kunci_interactive(kunci_dir),
            kunci_dir=kunci_dir,
            standard_dir=pipeline_factory.resolve_standard_dir(config, topic_id=topic_id),
            topic_id=topic_id,
        )

    def propose_crops(self, config: AppConfig, layout: RunLayout, pdf_path: Path) -> None:
        flows.propose_crops(config, layout, pdf_path)

    def recrop(self, config: AppConfig, layout: RunLayout) -> None:
        flows.recrop(config, layout)

    def label(self, config: AppConfig, layout: RunLayout, mode: LabelMode) -> None:
        flows.label(config, layout, mode)

    def finish(self, config: AppConfig, layout: RunLayout, topic_id: str | None) -> None:
        flows.finish_from_crops(config, layout, topic_id=topic_id)

    def finish_questions(
        self, config: AppConfig, layout: RunLayout, topic_id: str | None
    ) -> None:
        flows.finish_from_questions(config, layout, topic_id=topic_id)
