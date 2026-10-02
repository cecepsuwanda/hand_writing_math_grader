"""Pick the standards folder (kunci/rubric/schema) for the active topic."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.functions.standards_layout import topic_standard_dir


def resolve_standard_dir(
    config: AppConfig,
    *,
    topic_id: str | None = None,
    standard_dir: Path | None = None,
) -> Path:
    """Explicit ``standard_dir`` wins; else ``<standards_root>/topik_<bab>`` of the topic.

    Raises:
        UnknownTopicError: if the topic id is not a registered pack.
    """
    if standard_dir is not None:
        return Path(standard_dir)
    from app.topics.registry import get_pack

    explicit = topic_id if topic_id is not None and str(topic_id).strip() else None
    pack = get_pack(explicit or config.grading.topic_id)
    return topic_standard_dir(config.grading.standards_root, pack.id)
