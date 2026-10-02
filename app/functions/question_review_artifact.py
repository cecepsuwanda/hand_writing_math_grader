"""Load / fingerprint ``question.json`` files and drop stale LaTeX sidecars."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from app.functions.question_names import latex_source_filename, question_dir_name
from app.functions.validation_artifact import load_question_artifact, question_artifact_paths
from app.models.question import Question


def load_question_artifacts(
    questions_dir: Path,
) -> tuple[list[tuple[Path, Question]], list[str]]:
    """Parsed questions plus one error per unreadable / inconsistent file."""
    loaded: list[tuple[Path, Question]] = []
    errors: list[str] = []
    for path in question_artifact_paths(questions_dir):
        folder = path.parent.name
        try:
            question = load_question_artifact(path)
        except ValueError as exc:
            errors.append(f"{folder}/{path.name}: {exc}")
            continue
        problem = _consistency_error(question, folder)
        if problem is not None:
            errors.append(f"{folder}/{path.name}: {problem}")
            continue
        loaded.append((path, question))
    return loaded, errors


def _consistency_error(question: Question, folder: str) -> str | None:
    """Edits later stages cannot survive: wrong id/number for the folder, duplicate steps."""
    if question.question_id != folder:
        return f"question_id {question.question_id!r} tidak sama dengan nama folder"
    try:
        expected = question_dir_name(question.question_number)
    except ValueError as exc:
        return str(exc)
    if expected != folder:
        return (
            f"question_number {question.question_number} tidak sesuai dengan nama folder"
        )
    numbers = [step.step_number for step in question.student_steps]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        return f"step_number duplikat: {', '.join(str(n) for n in duplicates)}"
    return None


def question_fingerprints(questions_dir: Path) -> dict[str, str]:
    """Folder name → sha256 of its ``question.json`` bytes."""
    return {
        path.parent.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in question_artifact_paths(questions_dir)
    }


def stale_latex_sources(questions_dir: Path) -> list[str]:
    """Folders whose ``question.json`` was saved after its ``latex_source.tex``.

    Extract writes ``question.json`` first, so an untouched folder is never stale.
    """
    stale: list[str] = []
    for path in question_artifact_paths(questions_dir):
        sidecar = path.parent / latex_source_filename()
        if sidecar.is_file() and path.stat().st_mtime > sidecar.stat().st_mtime:
            stale.append(path.parent.name)
    return stale


def drop_latex_sources(questions_dir: Path, question_ids: Iterable[str]) -> list[Path]:
    """Remove ``latex_source.tex`` so ``student.tex`` is rebuilt from edited steps."""
    removed: list[Path] = []
    for question_id in question_ids:
        path = Path(questions_dir) / question_id / latex_source_filename()
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed
