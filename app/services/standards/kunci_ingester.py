"""Ingest kunci_jawaban TeX files into standards/solutions + exam_schema.json."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import AmbiguousKunciDirError, NoKunciTexError
from app.functions.kunci_ingest import (
    build_exam_schema,
    ingest_kunci_tex,
)
from app.functions.paths import list_kunci_tex
from app.functions.standard_extract import exam_schema_path, standard_solution_path
from app.interfaces.topic_pack import TopicPack
from app.models.exam_schema import ExamSchema
from app.topics.registry import DEFAULT_TOPIC_ID, get_pack

logger = logging.getLogger(__name__)

SOLUTIONS_DIRNAME = "solutions"
RUBRICS_DIRNAME = "rubrics"


class KunciIngester:
    """Write solutions, exam_schema.json, and part-based rubrics."""

    def __init__(
        self,
        standard_dir: Path,
        *,
        topic_pack: TopicPack | None = None,
        topic_id: str | None = None,
    ) -> None:
        self._standard_dir = Path(standard_dir)
        self._pack = topic_pack or get_pack(topic_id or DEFAULT_TOPIC_ID)

    @property
    def standard_dir(self) -> Path:
        return self._standard_dir

    @property
    def topic_pack(self) -> TopicPack:
        return self._pack

    def ingest_file(self, kunci_path: Path) -> list[Path]:
        kunci_path = Path(kunci_path)
        tex = kunci_path.read_text(encoding="utf-8")
        pairs = ingest_kunci_tex(tex, source_note=kunci_path.name)
        self._clear_previous_ingest()
        solutions_dir = self._standard_dir / SOLUTIONS_DIRNAME
        solutions_dir.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for number, content in pairs:
            path = standard_solution_path(self._standard_dir, number)
            path.write_text(content, encoding="utf-8")
            written.append(path)
            logger.info("Wrote standard solution %s", path)

        schema = build_exam_schema(
            tex,
            source=kunci_path.name,
            topic_id=self._pack.id,
        )
        schema_path = self._write_exam_schema(schema)
        written.append(schema_path)
        written.extend(self._write_rubrics(schema))
        return written

    def ingest_dir(self, kunci_dir: Path) -> list[Path]:
        """Ingest the single ``.tex`` under ``kunci_dir``.

        Raises:
            NoKunciTexError: if the folder has no ``.tex``.
            AmbiguousKunciDirError: if it has more than one (schema/rubrics
                come from one kunci, so merging files would mix exams).
        """
        kunci_dir = Path(kunci_dir)
        tex_files = list_kunci_tex(kunci_dir)
        if not tex_files:
            raise NoKunciTexError(kunci_dir)
        if len(tex_files) > 1:
            raise AmbiguousKunciDirError(kunci_dir, [path.name for path in tex_files])
        return self.ingest_file(tex_files[0])

    def _clear_previous_ingest(self) -> None:
        """Drop solutions/rubrics of an earlier kunci so no stale question survives."""
        for dirname, pattern in (
            (SOLUTIONS_DIRNAME, "question_*.tex"),
            (RUBRICS_DIRNAME, "question_*.json"),
        ):
            folder = self._standard_dir / dirname
            if not folder.is_dir():
                continue
            for stale in folder.glob(pattern):
                if stale.is_file():
                    stale.unlink()

    def _write_exam_schema(self, schema: ExamSchema) -> Path:
        self._standard_dir.mkdir(parents=True, exist_ok=True)
        path = exam_schema_path(self._standard_dir)
        path.write_text(schema.model_dump_json(indent=2), encoding="utf-8")
        logger.info(
            "Wrote exam schema %s (%s question(s), topic=%s)",
            path,
            len(schema.questions),
            schema.topic_id,
        )
        return path

    def _write_rubrics(self, schema: ExamSchema) -> list[Path]:
        rubrics_dir = self._standard_dir / RUBRICS_DIRNAME
        rubrics_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for question in schema.questions:
            rubric = self._pack.rubric_from_parts(question.number, question.parts)
            path = rubrics_dir / f"question_{question.number:03d}.json"
            path.write_text(rubric.model_dump_json(indent=2), encoding="utf-8")
            written.append(path)
            logger.info("Wrote rubric %s", path)
        return written
