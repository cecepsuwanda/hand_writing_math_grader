"""Limit topic pack (syllabus bab 4) — substitution, indeterminate forms, one-sided limits."""

from __future__ import annotations

from app.topics.chapter_pack import ChapterPack, MilestonePart

PACK = ChapterPack(
    pack_id="4",
    label="4 Limit",
    topik_refs=("4", "4.1", "4.2", "4.3", "4.4", "4.5"),
    milestones=(
        MilestonePart(
            role="indeterminate",
            points=1.0,
            titles=(r"^Coba\s+Substitusi\s+Langsung\b",),
            step_cue=(
                r"tak\s+tentu|indeterminate"
                r"|\\frac\s*\{\s*0\s*\}\s*\{\s*0\s*\}|(?<![\d.])0\s*/\s*0(?![\d.])"
            ),
            hint="direct substitution showing an indeterminate form (0/0, oo/oo)",
        ),
        MilestonePart(
            role="one_sided",
            points=2.0,
            titles=(r"^(?:Hitung\s+)?Limit\s+(?:Kiri|Kanan|Sepihak)\b",),
            step_cue=(
                r"limit\s+(?:kiri|kanan|sepihak)"
                r"|(?:->|\\to|→)\s*[^\s,)]+?\s*\^\s*\{?\s*[-+]"
                r"|Limit\((?:[^()]|\([^()]*\))*,\s*['\"]?[-+]['\"]?\s*\)"
            ),
            hint="a left / right limit (x -> a^- or x -> a^+)",
        ),
    ),
    algebra_hint=(
        "ordinary limit transformations (factor, multiply by the conjugate, "
        "divide by the highest power, trig base limits)"
    ),
    final_hint='the concluding limit value (e.g. "Jadi lim ... = 3", "limit tidak ada")',
)
