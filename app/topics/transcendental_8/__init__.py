"""Transcendental-function topic pack (syllabus bab 8) — ln / exp derivatives and integrals."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="8",
    label="8 Fungsi Transenden",
    topik_refs=("8", "8.1", "8.2", "8.3", "8.4", "8.5"),
    milestones=(
        MilestonePart(
            role="domain",
            points=1.0,
            titles=(r"^(?:Tentukan\s+)?Domain\b",),
            hint="the domain where the logarithm is defined (argument > 0)",
        ),
        MilestonePart(
            role="log_rule",
            points=1.5,
            titles=(
                r"^Uraikan\s+dengan\s+Sifat\s+Logaritma\b",
                r"^(?:Gunakan|Cek\s+dengan)\s+Rumus\b",
                r"^Tentukan\s+\$?\s*u\b",
            ),
            step_cue=r"\\frac\s*\{\s*u'\s*\}\s*\{\s*u\s*\}|\(\s*u'\s*\)\s*/\s*\(\s*u\s*\)",
            hint="(ln u)' = u'/u or a logarithm property (ln(a/b) = ln a - ln b)",
        ),
        MilestonePart(
            role="chain_rule",
            points=1.0,
            titles=(
                r"^Fungsi\s+Dalam\b",
                r"^Turunan\s+Setiap\s+Faktor\b",
                r"^Aturan\s+(?:Rantai|Hasil\s+Kali)\b",
            ),
            hint="the inner function / product rule for e^u, sin(ln u), ...",
        ),
        MilestonePart(
            role="substitution",
            points=1.5,
            titles=(
                r"^Pilih\s+\$?\s*u\b",
                r"^Pembilang\s+Kelipatan\b",
                r"^Ubah\s+Batas\b",
                r"^Substitusi\s+dan\s+(?:Integralkan|Hitung)\b",
            ),
            step_cue=r"(?<![A-Za-z])du\b|(?<![A-Za-z])u\s*=",
            hint="choosing u, du = u' dx, or the integral rewritten in u (int 1/u du = ln|u|)",
        ),
    ),
    algebra_hint="ordinary algebra (simplify, combine fractions, trig identities)",
    final_hint="the derivative f'(x), the antiderivative + C, or the integral value",
)
