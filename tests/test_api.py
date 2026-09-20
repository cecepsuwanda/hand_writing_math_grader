"""Tests for thin FastAPI adapter (no live Ollama)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from app.api import app, configure_process_factory
from app.models.grading import ReviewStatus
from app.models.process import ProcessResult, QuestionScoreSummary


@pytest.fixture(autouse=True)
def _reset_factory() -> None:
    configure_process_factory(None)
    yield
    configure_process_factory(None)


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_process_with_mock_controller(tmp_path: Path) -> None:
    fake_result = ProcessResult(
        student_id="s1",
        questions=[
            QuestionScoreSummary(
                question_id="question_001",
                question_number=1,
                score=8.0,
                maximum_score=10.0,
                review_status=ReviewStatus.AUTO_ACCEPT,
            )
        ],
        total_score=8.0,
        maximum_total=10.0,
        overall_status=ReviewStatus.AUTO_ACCEPT,
        output_dir=tmp_path / "out",
        report_json_path=tmp_path / "out" / "report.json",
        summary_csv_path=None,
        report_html_path=None,
        questions_dir=tmp_path / "questions",
        pages_dir=tmp_path / "pages",
        recognition_dir=tmp_path / "recognition",
    )

    pdf = tmp_path / "ans.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_controller = MagicMock()
    mock_controller.process.return_value = fake_result

    def factory(_config: object) -> MagicMock:
        return mock_controller

    configure_process_factory(factory)  # type: ignore[arg-type]

    # Point jawaban_dir at tmp via monkeypatch of load_config would be heavy;
    # pass absolute pdf path — resolve_jawaban_pdf accepts existing absolute files.
    client = TestClient(app)
    response = client.post(
        "/api/process",
        json={"pdf": str(pdf), "student_id": "s1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["student_id"] == "s1"
    assert payload["total_score"] == 8.0
    mock_controller.process.assert_called_once()


def test_api_results_reads_grading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import api as api_mod
    from app.config import AppConfig, GradingConfig, QuestionsConfig, ReportConfig

    qdir = tmp_path / "questions" / "question_001"
    qdir.mkdir(parents=True)
    (qdir / "grading.json").write_text('{"score": 1}', encoding="utf-8")

    cfg = AppConfig(
        questions=QuestionsConfig(output_dir=tmp_path / "questions"),
        grading=GradingConfig(standard_dir=tmp_path / "standards"),
        report=ReportConfig(output_dir=tmp_path),
    )
    monkeypatch.setattr(api_mod, "load_config", lambda path=None: cfg)

    client = TestClient(app)
    response = client.get("/api/results/question_001")
    assert response.status_code == 200
    assert response.json()["grading_path"].endswith("grading.json")
    assert "score" in response.json()["grading"]
