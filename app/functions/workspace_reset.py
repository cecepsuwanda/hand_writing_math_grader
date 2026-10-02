"""Empty one run folder (and overridden artifact dirs) before a new run (filesystem I/O)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.exceptions import UnsafeOutputDirError

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


def clear_directory_contents(directory: Path) -> list[str]:
    """Delete all children of ``directory``, creating it if missing."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        name = child.name
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
        removed.append(name)
        logger.info("Cleared directory child: %s", child)
    return removed


def ensure_resettable_dir(path: Path, *, run_root: Path, label: str) -> bool:
    """Whether ``path`` lies inside ``run_root`` and may therefore be emptied.

    A folder outside the run is never emptied: a missing or empty one is
    created (``False``); one that already holds files raises
    :class:`UnsafeOutputDirError`, as does the run root itself or any parent.
    """
    path = Path(path)
    run_root = Path(run_root)
    resolved = path.resolve()
    root_resolved = run_root.resolve()
    if root_resolved.is_relative_to(resolved):
        raise UnsafeOutputDirError(
            label, path, run_root, "Folder ini adalah folder run itu sendiri atau induknya"
        )
    if resolved.is_relative_to(root_resolved):
        return True
    if resolved.exists() and not resolved.is_dir():
        raise UnsafeOutputDirError(label, path, run_root, "Path ini bukan folder")
    if resolved.is_dir() and any(resolved.iterdir()):
        raise UnsafeOutputDirError(
            label, path, run_root, "Folder di luar folder run sudah berisi file"
        )
    path.mkdir(parents=True, exist_ok=True)
    return False


def reset_artifact_dir(path: Path, *, run_root: Path, label: str) -> list[str]:
    """Empty ``path`` when it is inside ``run_root``; see :func:`ensure_resettable_dir`."""
    if ensure_resettable_dir(path, run_root=run_root, label=label):
        return clear_directory_contents(path)
    return []


def prepare_pipeline_workspace(
    workspace_root: Path,
    *,
    pages_dir: Path,
    recognition_dir: Path,
    questions_dir: Path,
    crops_dir: Path | None = None,
    preserve: frozenset[str] | set[str] = DEFAULT_PRESERVE,
    keep_crops: bool = False,
) -> list[str]:
    """Clear ``workspace_root`` (except preserve); artifact dirs outside it are never emptied.

    Every artifact dir is checked before anything is deleted, so a refused
    override (:class:`UnsafeOutputDirError`) leaves the workspace intact.
    ``keep_crops`` leaves ``crops_dir`` untouched, inside or outside the root.
    """
    workspace_root = Path(workspace_root)
    root_resolved = workspace_root.resolve()

    extras: list[tuple[str, Path]] = [
        ("pages", Path(pages_dir)),
        ("recognition", Path(recognition_dir)),
        ("questions", Path(questions_dir)),
    ]
    if crops_dir is not None and not keep_crops:
        extras.append(("crops", Path(crops_dir)))
    for label, path in extras:
        ensure_resettable_dir(path, run_root=workspace_root, label=label)

    preserve_names = set(preserve)
    if keep_crops and crops_dir is not None:
        top = _top_level_name(Path(crops_dir), root_resolved)
        if top is not None:
            preserve_names.add(top)
    removed = clear_output_workspace(workspace_root, preserve=preserve_names)

    # Under root: already cleared with workspace; ensure paths exist for writers.
    for _label, path in extras:
        path.mkdir(parents=True, exist_ok=True)

    return removed


def _top_level_name(path: Path, root_resolved: Path) -> str | None:
    """First path segment of ``path`` under ``root_resolved``, or None if outside."""
    try:
        parts = path.resolve().relative_to(root_resolved).parts
    except ValueError:
        return None
    return parts[0] if parts else None
