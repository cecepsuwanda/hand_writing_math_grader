"""Topic pack registry — in-repo packs selectable by id."""

from __future__ import annotations

from app.exceptions import UnknownTopicError
from app.interfaces.topic_pack import TopicPack
from app.models.defaults import DEFAULT_TOPIC_ID
from app.models.exam_schema import ExamSchema
from app.topics.abs_inequality_2 import PACK as ABS_INEQUALITY_2
from app.topics.inequality_1_5 import PACK as INEQUALITY_15
from app.topics.runtime import get_active_pack

__all__ = [
    "DEFAULT_TOPIC_ID",
    "get_pack",
    "known_topic_ids",
    "list_packs",
    "resolve_pack",
]

_PACKS: dict[str, TopicPack] = {
    INEQUALITY_15.id: INEQUALITY_15,
    ABS_INEQUALITY_2.id: ABS_INEQUALITY_2,
}


def list_packs() -> list[TopicPack]:
    """Return registered packs sorted by id."""
    return [_PACKS[key] for key in sorted(_PACKS.keys())]


def known_topic_ids() -> list[str]:
    return sorted(_PACKS.keys())


def get_pack(topic_id: str | None = None) -> TopicPack:
    """Resolve a pack by id; default ``1.5``.

    Raises:
        UnknownTopicError: if ``topic_id`` is not registered.
    """
    tid = (topic_id or DEFAULT_TOPIC_ID).strip()
    pack = _PACKS.get(tid)
    if pack is None:
        raise UnknownTopicError(tid, known_topic_ids())
    return pack


def resolve_pack(
    *,
    topic_id: str | None = None,
    schema: ExamSchema | None = None,
) -> TopicPack:
    """Prefer explicit topic_id, then schema.topic_id, then active context, then default."""
    if topic_id is not None and topic_id.strip():
        return get_pack(topic_id)
    if schema is not None and (schema.topic_id or "").strip():
        return get_pack(schema.topic_id)
    active = get_active_pack()
    if active is not None:
        return active
    return get_pack(DEFAULT_TOPIC_ID)
