"""Tests for clearing data/output workspace."""

from pathlib import Path

from app.services.workspace.cleaner import (
    clear_output_workspace,
    prepare_pipeline_workspace,
)


def test_clear_output_workspace_preserves_standards(tmp_path: Path) -> None:
    root = tmp_path / "output"
    pages = root / "pages"
    pages.mkdir(parents=True)
    (pages / "page_001.png").write_bytes(b"x")
    (root / "report.json").write_text("{}", encoding="utf-8")
    standards = root / "standards" / "exam_001"
    standards.mkdir(parents=True)
    rubric = standards / "rubric.json"
    rubric.write_text("{}", encoding="utf-8")

    removed = clear_output_workspace(root)

    assert sorted(removed) == ["pages", "report.json"]
    assert not pages.exists()
    assert not (root / "report.json").exists()
    assert rubric.is_file()


def test_clear_output_workspace_creates_missing_root(tmp_path: Path) -> None:
    root = tmp_path / "missing-output"
    assert clear_output_workspace(root) == []
    assert root.is_dir()


def test_prepare_pipeline_workspace_clears_dirs_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "output"
    root.mkdir()
    (root / "stale.txt").write_text("x", encoding="utf-8")
    standards = root / "standards"
    standards.mkdir()
    (standards / "keep.txt").write_text("keep", encoding="utf-8")

    pages_dir = tmp_path / "external_pages"
    recognition_dir = tmp_path / "external_recognition"
    questions_dir = tmp_path / "external_questions"
    for directory in (pages_dir, recognition_dir, questions_dir):
        directory.mkdir()
        (directory / "old.bin").write_bytes(b"old")

    removed = prepare_pipeline_workspace(
        root,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
    )

    assert "stale.txt" in removed
    assert not (pages_dir / "old.bin").exists()
    assert not (recognition_dir / "old.bin").exists()
    assert not (questions_dir / "old.bin").exists()
    assert (standards / "keep.txt").is_file()
    assert pages_dir.is_dir()
