"""Integral topic pack (syllabus bab 7) — antiderivatives, properties, FTC I/II, substitution."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="7",
    label="7 Integral",
    topik_refs=("7", "7.1", "7.2", "7.3", "7.4", "7.5"),
    milestones=(
        MilestonePart(
            role="antiderivative",
            points=1.0,
            titles=(r"^Cari\s+Anti\s*Turunan\b", r"^Integralkan\s+per\s+Suku\b"),
            step_cue=r"\+\s*C\b",
            hint="an antiderivative F(x) (+ C)",
        ),
        MilestonePart(
            role="integral_property",
            points=1.0,
            titles=(
                r"^Keluarkan\s+Konstanta\b",
                r"^Sifat\s+(?:Linear|Aditif)\b",
                r"^Batas\s+Ditukar\b",
            ),
            hint="a linearity / additivity / swapped-bounds property of the definite integral",
        ),
        MilestonePart(
            role="ftc",
            points=1.0,
            titles=(
                r"^Kenali\s+Integran\b",
                r"^Gunakan\s+Rumus\b.*\bTDK\b",
                r"^Substitusikan\s+Batas\s+(?:ke\s+Integran|dan\s+Gunakan)\b",
            ),
            step_cue=r"\bG\s*'\s*\(",
            hint="the first fundamental theorem: G'(x) = f(v(x)) v'(x) - f(u(x)) u'(x)",
        ),
        MilestonePart(
            role="substitution",
            points=1.5,
            titles=(
                r"^Pilih\s+\$?\s*u\b",
                r"^Ubah\s+Batas\b",
                r"^Substitusi\s+dan\s+(?:Integralkan|Hitung)\b",
            ),
            step_cue=r"(?<![A-Za-z])du\b|(?<![A-Za-z])u\s*=",
            hint="choosing u = g(x), du = g'(x) dx, or the integral rewritten in u",
        ),
        MilestonePart(
            role="evaluate_bounds",
            points=1.0,
            titles=(r"^Substitusikan\s+Batas\s+dan\s+Kurangkan\b",),
            step_cue=r"\\[bB]igr\s*\]|\]\s*_",
            hint="F(b) - F(a) with the bounds substituted",
        ),
    ),
    algebra_hint="ordinary algebra (expand, divide each term, simplify)",
    final_hint="the integral value or the antiderivative + C / G'(x)",
)
