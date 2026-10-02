"""Per-topic standards folder naming (``<standards_root>/topik_<bab>``)."""

from __future__ import annotations

from pathlib import Path

STANDARDS_FOLDER_PREFIX = "topik_"


def standards_folder_name(topic_id: str) -> str:
    """Folder for a topic pack: the syllabus chapter (bab) of its id.

    ``"1.5"`` → ``topik_1``, ``"2"`` → ``topik_2``.

    Raises:
        ValueError: if ``topic_id`` has no chapter number.
    """
    chapter = str(topic_id).strip().split(".")[0].strip()
    if not chapter:
        raise ValueError(f"topic id has no chapter number: {topic_id!r}")
    return f"{STANDARDS_FOLDER_PREFIX}{chapter}"


def topic_standard_dir(standards_root: Path, topic_id: str) -> Path:
    return Path(standards_root) / standards_folder_name(topic_id)
