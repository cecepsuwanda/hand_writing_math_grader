"""Ingest kunci_jawaban TeX files into standards/solutions."""

from __future__ import annotations

import logging
from pathlib import Path

from app.functions.kunci_ingest import ingest_kunci_tex
from app.functions.standard_extract import standard_solution_path

logger = logging.getLogger(__name__)


class KunciIngester:
    """Write ``solutions/question_NNN.tex`` from kunci TeX (rubrics untouched)."""

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
        return written

    def ingest_dir(self, kunci_dir: Path) -> list[Path]:
        kunci_dir = Path(kunci_dir)
        written: list[Path] = []
        for path in sorted(kunci_dir.glob("*.tex")):
            written.extend(self.ingest_file(path))
        return written
