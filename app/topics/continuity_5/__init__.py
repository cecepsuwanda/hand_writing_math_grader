"""Continuity topic pack (syllabus bab 5) — f(a), one-sided limits, the three conditions."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="5",
    label="5 Kekontinuan",
    topik_refs=("5", "5.1", "5.2"),
    milestones=(
        MilestonePart(
            role="one_sided",
            points=1.5,
            titles=(
                r"^(?:Hitung\s+)?Limit\s+(?:Kiri|Kanan|Sepihak)\b",
                r"^Hitung\b.*\bLimit\s+(?:Kiri|Kanan|Sepihak)\b",
            ),
            step_cue=(
                r"limit\s+(?:kiri|kanan|sepihak)"
                r"|(?:->|\\to|→)\s*[^\s,)]+?\s*\^\s*\{?\s*[-+]"
                r"|Limit\((?:[^()]|\([^()]*\))*,\s*['\"]?[-+]['\"]?\s*\)"
            ),
            hint="a left / right limit at the point (x -> a^- or x -> a^+)",
        ),
        MilestonePart(
            role="function_value",
            points=1.0,
            titles=(r"^Hitung\s+\$?\s*f\s*\(",),
            step_cue=r"^\s*[fghk]\s*\(\s*-?[\d.,/]+\s*\)\s*=",
            hint="the function value f(a) at the point",
        ),
        MilestonePart(
            role="continuity",
            points=1.5,
            titles=(
                r"^Bandingkan\b",
                r"^Syarat\s+Kontinu\b",
                r"^Kekontinuan\s+di\b",
                r"^Samakan\b",
            ),
            step_cue=r"\bkontinu|\bcontinuous",
            hint="comparing lim f(x) with f(a) / the continuity condition equation",
        ),
    ),
    figure_kinds=("graph",),
    figure_titles=(r"^Gambar(?:kan)?\s+Grafik\b",),
    algebra_hint="ordinary algebra (simplify, solve for the constants)",
    final_hint="the conclusion (kontinu / tidak kontinu at the point, or the constants found)",
)
