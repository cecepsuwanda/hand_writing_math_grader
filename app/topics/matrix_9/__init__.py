"""Matrix topic pack (syllabus bab 9) — size, entrywise operations, transpose, trace."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="9",
    label="9 Matriks",
    topik_refs=("9", "9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7"),
    milestones=(
        MilestonePart(
            role="size_check",
            points=1.0,
            titles=(r"^Periksa\s+Ukuran\b",),
            hint="checking the sizes (m x n) so the operation is defined",
        ),
        MilestonePart(
            role="transpose",
            points=1.5,
            titles=(
                r"^Transposkan\b",
                r"^Cek\s+dengan\s+Sifat\s+\$?\s*\(\s*AB\s*\)",
                r"^(?:Cara\s+Cepat|Penjelasan)\s+dengan\s+Sifat\s+Transpos\b",
            ),
            hint="a transpose A^T or a transpose property ((AB)^T = B^T A^T)",
        ),
        MilestonePart(
            role="trace",
            points=1.5,
            titles=(r"^Jumlahkan\s+Diagonal\s+Utama\b", r"^Cek\s+dengan\s+Sifat\s+Trace\b"),
            step_cue=r"\\operatorname\s*\{\s*tr\s*\}|TRACE\(|(?<![A-Za-z])tr\s*\(",
            hint="the trace tr(A) = sum of the main diagonal (or a trace property)",
        ),
        MilestonePart(
            role="matrix_equation",
            points=1.5,
            titles=(r"^Samakan\s+Entri\b", r"^Eliminasi\b"),
            hint="equating corresponding entries and solving the resulting system",
        ),
    ),
    algebra_hint="entrywise matrix arithmetic (add, scalar multiple, row-by-column product)",
    final_hint="the resulting matrix, the trace value, or the unknown entries",
)
