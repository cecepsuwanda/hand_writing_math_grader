"""Vector topic pack (syllabus bab 11) — components, norm / distance, dot, cross, triple product."""

from __future__ import annotations

from app.capabilities.registry import ALL_CAPABILITY_IDS
from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="11",
    label="11 Vektor",
    topik_refs=("11", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "11.7", "11.8"),
    milestones=(
        MilestonePart(
            role="components",
            points=1.0,
            titles=(r"^Ujung\s+Dikurangi\s+Pangkal\b",),
            step_cue=r"\\overrightarrow",
            hint="vector components: terminal point minus initial point",
        ),
        MilestonePart(
            role="norm",
            points=1.5,
            titles=(r"^Jarak\s+sebagai\s+Norm\b", r"^Hitung\s+Norm\b"),
            step_cue=r"\\\||\\lVert|NORM\(",
            hint="a norm ||u|| = sqrt(u1^2 + u2^2 + u3^2) or a distance",
        ),
        MilestonePart(
            role="dot",
            points=1.5,
            titles=(
                r"^(?:Aturan\s+Tanda\s+|Hitung\s+)?Hasil\s+Kali\s+Titik\b",
                r"^Cek\s+Tegak\s+Lurus\b",
            ),
            step_cue=r"\\mathbf\s*\{\s*\w+\s*\}\s*\\cdot|DOT\(",
            hint="a dot product u . v (sign decides acute / obtuse / perpendicular)",
        ),
        MilestonePart(
            role="cross",
            points=1.5,
            titles=(
                r"^Gunakan\s+Hasil\s+Kali\s+Silang\b",
                r"^Hitung\s+Ketiga\s+Minor\b",
                r"^Cara\s+Alternatif\b.*\bSilang\b",
                r"^Determinan\s+dengan\s+Ekspansi\b",
            ),
            step_cue=r"\\mathbf\s*\{\s*\w+\s*\}\s*\\times|CROSS\(",
            hint="a cross product u x v (i, j, k determinant) or the triple product",
        ),
    ),
    algebra_hint="componentwise arithmetic and simplifying roots",
    final_hint="the resulting vector, norm / distance, triple product, or the angle type",
    capability_ids=ALL_CAPABILITY_IDS + ("vector_tuple",),
)
