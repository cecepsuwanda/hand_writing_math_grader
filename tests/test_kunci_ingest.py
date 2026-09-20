"""Tests for kunci_jawaban TeX ingest → standards/solutions."""

from __future__ import annotations

from pathlib import Path

from app.controllers.ingest_kunci_controller import IngestKunciController
from app.functions.kunci_ingest import (
    extract_align_steps,
    extract_hp_final,
    ingest_kunci_tex,
    split_enumerate_items,
)
from app.functions.standard_extract import extract_final_answer_from_tex
from app.services.standards.kunci_ingester import KunciIngester

_MINI_KUNCI = r"""
\begin{document}
\begin{enumerate}
    \item $2-3x \le 12$
    \begin{itemize}
    \item Langkah-langkah
    \begin{align}
    2 - 3x &\leq 12 \quad \text{(awal)} \\
    x &\geq -\frac{10}{3}
    \end{align}
    \item HP: $\left[-\frac{10}{3}, \infty\right)$
    \end{itemize}

    \item $3x-5 < 4x-6$
    \begin{itemize}
    \item Langkah-langkah
    \begin{align}
    3x - 5 &< 4x - 6 \\
    x &> 1
    \end{align}
    \item HP: $(1, \infty)$
    \end{itemize}
\end{enumerate}
\end{document}
"""


def test_split_enumerate_items_mini() -> None:
    items = split_enumerate_items(_MINI_KUNCI)
    assert len(items) == 2
    assert "2-3x" in items[0]
    assert "3x-5" in items[1]


def test_extract_hp_and_steps_mini() -> None:
    items = split_enumerate_items(_MINI_KUNCI)
    steps = extract_align_steps(items[0])
    assert len(steps) >= 2
    assert "text" not in steps[0].lower()
    assert extract_hp_final(items[0]) is not None
    assert "10" in (extract_hp_final(items[0]) or "")


def test_ingest_kunci_tex_pairs() -> None:
    pairs = ingest_kunci_tex(_MINI_KUNCI, source_note="mini")
    assert len(pairs) == 2
    assert pairs[0][0] == 1
    final = extract_final_answer_from_tex(pairs[0][1])
    assert final is not None
    assert "10" in final


def test_ingester_writes_solutions(tmp_path: Path) -> None:
    kunci = tmp_path / "kunci.tex"
    kunci.write_text(_MINI_KUNCI, encoding="utf-8")
    standard = tmp_path / "standards" / "exam"
    (standard / "rubrics").mkdir(parents=True)
    (standard / "rubrics" / "keep.json").write_text("{}", encoding="utf-8")

    written = KunciIngester(standard).ingest_file(kunci)
    assert len(written) == 2
    assert (standard / "solutions" / "question_001.tex").is_file()
    assert (standard / "solutions" / "question_002.tex").is_file()
    assert (standard / "rubrics" / "keep.json").is_file()


def test_controller_ingest_dir(tmp_path: Path) -> None:
    kunci_dir = tmp_path / "kunci"
    kunci_dir.mkdir()
    (kunci_dir / "a.tex").write_text(_MINI_KUNCI, encoding="utf-8")
    standard = tmp_path / "std"
    result = IngestKunciController().ingest(
        kunci_path=None,
        kunci_dir=kunci_dir,
        standard_dir=standard,
    )
    assert len(result.written) == 2


def test_repo_jawaban_tugas_1_at_least_six() -> None:
    path = Path("data/input/kunci_jawaban/jawaban_tugas_1.tex")
    assert path.is_file()
    pairs = ingest_kunci_tex(path.read_text(encoding="utf-8"), source_note=path.name)
    assert len(pairs) >= 6
    q1_final = extract_final_answer_from_tex(pairs[0][1])
    assert q1_final is not None
    assert "10" in q1_final and "3" in q1_final
