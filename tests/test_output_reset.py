"""Tests for clearing data/output workspace."""

from pathlib import Path

from app.functions.output_reset import clear_output_workspace


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
