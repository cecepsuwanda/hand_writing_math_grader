"""Filesystem helpers for pipeline workspace reset."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PRESERVE = frozenset({"standards"})


def clear_output_workspace(
    output_root: Path,
    *,
    preserve: frozenset[str] | set[str] = DEFAULT_PRESERVE,
) -> list[str]:
    """Delete contents of ``output_root`` except preserved top-level names.

    ``standards/`` is preserved by default so rubrics/solutions survive a run reset.
    Missing ``output_root`` is created empty.

    Returns:
        Names of removed top-level entries.
    """
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    preserve_names = {name.lower() for name in preserve}
    removed: list[str] = []

    for child in sorted(output_root.iterdir(), key=lambda p: p.name.lower()):
        if child.name.lower() in preserve_names:
            continue
        name = child.name
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
        removed.append(name)
        logger.info("Cleared output artifact: %s", child)

    return removed
