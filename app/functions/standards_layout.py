"""Per-topic folder naming (``topik_<bab>``) for standards, jawaban, and runs."""

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


def topic_jawaban_dir(jawaban_root: Path, topic_id: str) -> Path:
    """``<jawaban_root>/topik_<bab>`` for student PDFs of the active topic."""
    return Path(jawaban_root) / standards_folder_name(topic_id)


def topic_runs_root(output_root: Path, topic_id: str) -> Path:
    """``<output_root>/topik_<bab>`` holding per-PDF run folders."""
    return Path(output_root) / standards_folder_name(topic_id)


def is_topic_bucket_name(name: str) -> bool:
    """True for reserved ``topik_<bab>`` bucket folders (not a run name)."""
    lowered = (name or "").strip().lower()
    if not lowered.startswith(STANDARDS_FOLDER_PREFIX):
        return False
    suffix = lowered[len(STANDARDS_FOLDER_PREFIX) :]
    return bool(suffix) and suffix.isdigit()
