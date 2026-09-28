"""Topic packs — user-selectable syllabus-focused grading plugins."""

from app.topics.registry import (
    DEFAULT_TOPIC_ID,
    get_pack,
    known_topic_ids,
    list_packs,
    register_pack,
    resolve_pack,
)

__all__ = [
    "DEFAULT_TOPIC_ID",
    "get_pack",
    "known_topic_ids",
    "list_packs",
    "register_pack",
    "resolve_pack",
]
