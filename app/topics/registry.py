"""Topic pack registry — in-repo packs selectable by id."""

from __future__ import annotations

from app.exceptions import UnknownTopicError
from app.functions.standards_layout import standards_folder_name
from app.interfaces.topic_pack import TopicPack
from app.models.defaults import DEFAULT_TOPIC_ID
from app.models.exam_schema import ExamSchema
from app.topics.abs_inequality_2 import PACK as ABS_INEQUALITY_2
from app.topics.continuity_5 import PACK as CONTINUITY_5
from app.topics.derivative_6 import PACK as DERIVATIVE_6
from app.topics.determinant_10 import PACK as DETERMINANT_10
from app.topics.function_3 import PACK as FUNCTION_3
from app.topics.inequality_1_5 import PACK as INEQUALITY_15
from app.topics.integral_7 import PACK as INTEGRAL_7
from app.topics.limit_4 import PACK as LIMIT_4
from app.topics.matrix_9 import PACK as MATRIX_9
from app.topics.runtime import get_active_pack
from app.topics.transcendental_8 import PACK as TRANSCENDENTAL_8
from app.topics.vector_11 import PACK as VECTOR_11

__all__ = [
    "DEFAULT_TOPIC_ID",
    "assert_unique_standards_folders",
    "get_pack",
    "known_topic_ids",
    "list_packs",
    "resolve_pack",
]

_PACKS: dict[str, TopicPack] = {
    INEQUALITY_15.id: INEQUALITY_15,
    ABS_INEQUALITY_2.id: ABS_INEQUALITY_2,
    FUNCTION_3.id: FUNCTION_3,
    LIMIT_4.id: LIMIT_4,
    CONTINUITY_5.id: CONTINUITY_5,
    DERIVATIVE_6.id: DERIVATIVE_6,
    INTEGRAL_7.id: INTEGRAL_7,
    TRANSCENDENTAL_8.id: TRANSCENDENTAL_8,
    MATRIX_9.id: MATRIX_9,
    DETERMINANT_10.id: DETERMINANT_10,
    VECTOR_11.id: VECTOR_11,
}


def assert_unique_standards_folders(pack_ids: list[str]) -> None:
    """Two packs sharing ``topik_<bab>`` would overwrite each other's ingest.

    Raises:
        ValueError: on a folder collision.
    """
    seen: dict[str, str] = {}
    for pack_id in pack_ids:
        folder = standards_folder_name(pack_id)
        if folder in seen:
            raise ValueError(
                f"topic packs {seen[folder]!r} and {pack_id!r} share standards folder {folder}"
            )
        seen[folder] = pack_id


assert_unique_standards_folders(list(_PACKS))


def _syllabus_order(topic_id: str) -> tuple[int, ...]:
    """``"1.5" < "2" < "10"`` (chapter order, not string order)."""
    return tuple(int(part) for part in topic_id.split("."))


def list_packs() -> list[TopicPack]:
    """Return registered packs in syllabus order."""
    return [_PACKS[key] for key in known_topic_ids()]


def known_topic_ids() -> list[str]:
    return sorted(_PACKS.keys(), key=_syllabus_order)


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
