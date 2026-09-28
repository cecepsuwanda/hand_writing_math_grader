"""Infer / coalesce step roles for recognition → grading (pack delegate)."""

from __future__ import annotations

from app.models.recognition import SymbolicPayload
from app.topics.registry import resolve_pack


def coalesce_step_role(
    raw_text: str,
    symbolic: SymbolicPayload | None,
    role: str | None,
    *,
    topic_id: str | None = None,
) -> str:
    """Return a concrete step role via the active / resolved TopicPack."""
    pack = resolve_pack(topic_id=topic_id)
    return pack.coalesce_step_role(raw_text, symbolic, role)
