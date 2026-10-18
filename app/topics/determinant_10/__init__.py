"""Determinant / inverse topic pack (syllabus bab 10) — cofactor expansion, adjugate inverse."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="10",
    label="10 Determinan dan Invers",
    topik_refs=("10", "10.1", "10.2", "10.3"),
    milestones=(
        MilestonePart(
            role="determinant",
            points=1.5,
            titles=(
                r"^(?:Hitung\s+)?Determinan\b",
                r"^(?:Tulis\s+)?Ekspansi\b",
                r"^Pilih\s+Baris\b",
                r"^Jumlahkan\s+dengan\s+Tanda\b",
                r"^Cek\s+dengan\s+OBE\b",
            ),
            step_cue=r"\\det\b|DET\(|\\begin\s*\{\s*vmatrix\s*\}",
            hint="a determinant (cofactor expansion along a row, or ad - bc)",
        ),
        MilestonePart(
            role="cofactor",
            points=1.5,
            titles=(r"^Hitung\b.*\b(?:Kofaktor|Minor)\b", r"^Matriks\s+Kofaktor\b"),
            step_cue=r"(?<![A-Za-z])[CM]\s*_\s*\{?\s*\d\s*,?\s*\d",
            hint="a minor M_ij / cofactor C_ij, the cofactor matrix or adj(A) = C^T",
        ),
        MilestonePart(
            role="inverse",
            points=1.5,
            titles=(r"^Bagi\s+dengan\s+Determinan\b",),
            step_cue=r"\^\s*\{\s*-\s*1\s*\}|\^\s*-1\b|INV\(",
            hint="A^-1 = adj(A) / det(A)",
        ),
        MilestonePart(
            role="singular_condition",
            points=1.0,
            titles=(r"^Syarat\s+Tidak\s+Memiliki\s+Invers\b", r"^Eliminasi\b"),
            hint="det = 0 (singular) and solving the resulting conditions",
        ),
    ),
    algebra_hint="ordinary arithmetic / algebra and the verification A A^-1 = I",
    final_hint="the determinant value, the inverse matrix, or the parameter values",
)
