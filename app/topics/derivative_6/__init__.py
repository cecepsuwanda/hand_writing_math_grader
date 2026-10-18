"""Derivative topic pack (syllabus bab 6) — definition, one-sided derivatives, tangent lines."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="6",
    label="6 Turunan",
    topik_refs=("6", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7"),
    milestones=(
        MilestonePart(
            role="definition",
            points=1.0,
            titles=(r"^Tulis\s+Definisi\b", r"^Bagi\s+dengan\b.*\bLimit\b"),
            step_cue=r"f\s*\(\s*x\s*\+\s*h\s*\)",
            hint="the limit definition f'(x) = lim_{h->0} (f(x+h) - f(x))/h",
        ),
        MilestonePart(
            role="one_sided_derivative",
            points=1.5,
            titles=(r"^Hitung\s+Turunan\s+Kiri\b", r"^Turunan\s+(?:Kiri|Kanan|Sepihak)\b"),
            step_cue=r"f'\s*_\s*\{?\s*[-+]|turunan\s+(?:kiri|kanan|sepihak)",
            hint="a left / right derivative f'_-(a) or f'_+(a)",
        ),
        MilestonePart(
            role="tangent_line",
            points=1.5,
            titles=(
                r"^(?:Hitung\s+)?Kemiringan\s+Garis\s+Singgung\b",
                r"^Garis\s+(?:Singgung|Normal)\b",
            ),
            step_cue=r"garis\s+(?:singgung|normal)|\bm_?\{?n\}?\s*=|y\s*-\s*-?[\d.]+\s*=",
            hint="the slope m = f'(a) or the tangent / normal line equation",
        ),
    ),
    figure_kinds=("graph",),
    figure_titles=(r"^Gambar(?:kan)?\b",),
    algebra_hint="ordinary differentiation / algebra (product, quotient, chain rule, simplify)",
    final_hint="the derivative found, or the line equation / the (non)differentiability conclusion",
)
