"""Tests for input path resolution helpers."""

from pathlib import Path

import pytest

from app.functions.paths import (
    list_jawaban_pdfs,
    parse_pdf_choice,
    resolve_jawaban_pdf,
)


def test_resolve_jawaban_pdf_prefers_existing_path(tmp_path: Path) -> None:
    pdf = tmp_path / "direct.pdf"
    pdf.write_bytes(b"%PDF")
    jawaban = tmp_path / "jawaban"
    jawaban.mkdir()
    assert resolve_jawaban_pdf(pdf, jawaban) == pdf


def test_resolve_jawaban_pdf_finds_bare_name_under_jawaban(tmp_path: Path) -> None:
    jawaban = tmp_path / "jawaban"
    jawaban.mkdir()
    pdf = jawaban / "smoke_inequality.pdf"
    pdf.write_bytes(b"%PDF")
    assert resolve_jawaban_pdf(Path("smoke_inequality.pdf"), jawaban) == pdf


def test_resolve_jawaban_pdf_returns_original_when_missing(tmp_path: Path) -> None:
    missing = Path("missing.pdf")
    assert resolve_jawaban_pdf(missing, tmp_path / "jawaban") == missing


def test_list_jawaban_pdfs_sorted(tmp_path: Path) -> None:
    jawaban = tmp_path / "jawaban"
    jawaban.mkdir()
    (jawaban / "b.pdf").write_bytes(b"%PDF")
    (jawaban / "a.PDF").write_bytes(b"%PDF")
    (jawaban / "notes.txt").write_text("x", encoding="utf-8")
    (jawaban / "subdir").mkdir()
    names = [p.name for p in list_jawaban_pdfs(jawaban)]
    assert names == ["a.PDF", "b.pdf"]


def test_parse_pdf_choice_by_index_and_name(tmp_path: Path) -> None:
    pdfs = [tmp_path / "one.pdf", tmp_path / "two.pdf"]
    for pdf in pdfs:
        pdf.write_bytes(b"%PDF")
    assert parse_pdf_choice(pdfs, "2") == pdfs[1]
    assert parse_pdf_choice(pdfs, "one.pdf") == pdfs[0]
    assert parse_pdf_choice(pdfs, "TWO") == pdfs[1]
    with pytest.raises(ValueError):
        parse_pdf_choice(pdfs, "9")
