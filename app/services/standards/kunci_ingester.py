"""Ingest kunci_jawaban TeX files into standards/solutions + exam_schema.json."""

from __future__ import annotations

import logging
from pathlib import Path

from app.functions.kunci_ingest import build_exam_schema, ingest_kunci_tex
from app.functions.standard_extract import exam_schema_path, standard_solution_path
from app.models.exam_schema import ExamSchema

logger = logging.getLogger(__name__)


class KunciIngester:
    """Write ``solutions/question_NNN.tex`` and ``exam_schema.json`` (rubrics untouched)."""

    def __init__(self, standard_dir: Path) -> None:
        self._standard_dir = Path(standard_dir)

    def ingest_file(self, kunci_path: Path) -> list[Path]:
        kunci_path = Path(kunci_path)
        tex = kunci_path.read_text(encoding="utf-8")
        pairs = ingest_kunci_tex(tex, source_note=kunci_path.name)
        solutions_dir = self._standard_dir / "solutions"
        solutions_dir.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for number, content in pairs:
            path = standard_solution_path(self._standard_dir, number)
            path.write_text(content, encoding="utf-8")
            written.append(path)
            logger.info("Wrote standard solution %s", path)

        schema = build_exam_schema(tex, source=kunci_path.name)
        schema_path = self._write_exam_schema(schema)
        written.append(schema_path)
        return written

    def ingest_dir(self, kunci_dir: Path) -> list[Path]:
        kunci_dir = Path(kunci_dir)
        written: list[Path] = []
        tex_files = sorted(kunci_dir.glob("*.tex"))
        if not tex_files:
            return written
        # First file drives schema + solutions; additional files append solutions only
        # then rebuild schema from the first (exam) file for a stable recognition source.
        for index, path in enumerate(tex_files):
            if index == 0:
                written.extend(self.ingest_file(path))
            else:
                tex = path.read_text(encoding="utf-8")
                pairs = ingest_kunci_tex(tex, source_note=path.name)
                for number, content in pairs:
                    out = standard_solution_path(self._standard_dir, number)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(content, encoding="utf-8")
                    written.append(out)
                    logger.info("Wrote standard solution %s", out)
        return written

    def _write_exam_schema(self, schema: ExamSchema) -> Path:
        self._standard_dir.mkdir(parents=True, exist_ok=True)
        path = exam_schema_path(self._standard_dir)
        path.write_text(schema.model_dump_json(indent=2), encoding="utf-8")
        logger.info(
            "Wrote exam schema %s (%s question(s))",
            path,
            len(schema.questions),
        )
        return path
