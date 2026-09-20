"""Tests for Phase 9 process CLI and ProcessController."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.cli import main
from app.controllers.process_controller import ProcessController
from app.exceptions import PdfNotFoundError
from app.models.grading import GradeResult, QuestionGrade, ReviewStatus
from app.models.page import Page, RenderResult
from app.models.process import ProcessStage
from app.models.recognition import RecognizeResult
from app.models.report import (
    ExamReport,
    PromptVersions,
    QuestionReportRow,
    ReportMetadata,
    ReportResult,
)
from app.models.question import ExtractResult
from app.models.latex import LatexResult
from app.models.validation import ValidateResult


def _page() -> Page:
    return Page(page_number=1, image="page_001.png", width=100, height=100)


def _grade() -> QuestionGrade:
    return QuestionGrade(
        question_id="question_001",
        question_number=1,
        score=8.0,
        maximum_score=10.0,
        review_status=ReviewStatus.AUTO_ACCEPT,
    )


def _report_result(tmp_path: Path) -> ReportResult:
    out = tmp_path / "output"
    meta = ReportMetadata(
        generated_at="2026-01-01T00:00:00+00:00",
        standard_dir=tmp_path / "standards",
        questions_dir=tmp_path / "questions",
        student_id="student_001",
        prompt_versions=PromptVersions(),
    )
    exam = ExamReport(
        metadata=meta,
        questions=[
            QuestionReportRow(
                question_id="question_001",
                question_number=1,
                score=8.0,
                maximum_score=10.0,
                review_status=ReviewStatus.AUTO_ACCEPT,
                step_count=2,
            )
        ],
        total_score=8.0,
        maximum_total=10.0,
        overall_status=ReviewStatus.AUTO_ACCEPT,
    )
    return ReportResult(
        exam_report=exam,
        output_dir=out,
        report_json_path=out / "report.json",
        summary_csv_path=out / "summary.csv",
        report_html_path=out / "report.html",
    )


def test_process_controller_runs_all_stages(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    recognition_dir = tmp_path / "recognition"
    questions_dir = tmp_path / "questions"
    output_dir = tmp_path / "output"
    pdf = tmp_path / "answer.pdf"
    pdf.write_bytes(b"%PDF")

    render = MagicMock()
    render.render.return_value = RenderResult(
        pages=[_page()],
        output_dir=pages_dir,
        metadata_path=pages_dir / "pages.json",
    )
    recognize = MagicMock()
    recognize.recognize_pages.return_value = RecognizeResult(
        pages=[], output_dir=recognition_dir, artifact_paths=[]
    )
    extract = MagicMock()
    extract.extract.return_value = ExtractResult(
        questions=[], output_dir=questions_dir, artifact_paths=[]
    )
    latex = MagicMock()
    latex.build.return_value = LatexResult(artifacts=[], questions_dir=questions_dir)
    validate = MagicMock()
    validate.validate.return_value = ValidateResult(
        validations=[], questions_dir=questions_dir, artifact_paths=[]
    )
    grade = MagicMock()
    grade.grade.return_value = GradeResult(
        grades=[_grade()],
        questions_dir=questions_dir,
        standard_dir=tmp_path / "standards",
        artifact_paths=[],
    )
    report = MagicMock()
    report.report.return_value = _report_result(tmp_path)

    progress_events: list[ProcessStage] = []
    cleared: list[tuple[Path, list[str]]] = []

    # Seed stale artifacts that must be cleared (standards preserved).
    output_dir.mkdir(parents=True)
    stale = output_dir / "pages"
    stale.mkdir()
    (stale / "old.png").write_bytes(b"x")
    standards = output_dir / "standards"
    standards.mkdir()
    (standards / "keep.txt").write_text("keep", encoding="utf-8")

    controller = ProcessController(
        render_controller=render,
        recognize_controller=recognize,
        extract_controller=extract,
        latex_controller=latex,
        validate_controller=validate,
        grade_controller=grade,
        report_controller=report,
        on_progress=lambda p: progress_events.append(p.stage),
        on_output_cleared=lambda root, names: cleared.append((root, names)),
    )
    result = controller.process(
        pdf,
        pages_dir=pages_dir,
        recognition_dir=recognition_dir,
        questions_dir=questions_dir,
        output_dir=output_dir,
        dpi=200,
        student_id="student_001",
        workspace_root=output_dir,
    )

    assert progress_events == [
        ProcessStage.RENDER,
        ProcessStage.RECOGNIZE,
        ProcessStage.EXTRACT,
        ProcessStage.LATEX,
        ProcessStage.VALIDATE,
        ProcessStage.GRADE,
        ProcessStage.REPORT,
    ]
    assert cleared and cleared[0][0] == output_dir
    assert "pages" in cleared[0][1]
    assert not stale.exists()
    assert (standards / "keep.txt").is_file()
    assert result.total_score == pytest.approx(8.0)
    assert result.maximum_total == pytest.approx(10.0)
    assert len(result.questions) == 1
    render.render.assert_called_once()
    recognize.recognize_pages.assert_called_once()
    extract.extract.assert_called_once()
    latex.build.assert_called_once()
    validate.validate.assert_called_once()
    grade.grade.assert_called_once()
    report.report.assert_called_once()


def test_cli_process_success(tmp_path: Path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "answer.pdf"
    pdf.write_bytes(b"%PDF")
    questions_dir = tmp_path / "questions"
    output_dir = tmp_path / "output"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "ollama:",
                '  vision_model: "vision-test"',
                '  reasoning_model: "reason-test"',
                "pdf:",
                f"  output_dir: {(tmp_path / 'pages').as_posix()}",
                "recognition:",
                f"  output_dir: {(tmp_path / 'recognition').as_posix()}",
                "questions:",
                f"  output_dir: {questions_dir.as_posix()}",
                "grading:",
                f"  standard_dir: {(tmp_path / 'standards').as_posix()}",
                "report:",
                f"  output_dir: {output_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    fake_result = MagicMock()
    fake_result.student_id = "student_001"
    fake_result.questions = [
        MagicMock(
            question_number=1,
            score=8.0,
            maximum_score=10.0,
            review_status=ReviewStatus.AUTO_ACCEPT,
        )
    ]
    fake_result.total_score = 8.0
    fake_result.maximum_total = 10.0
    fake_result.overall_status = ReviewStatus.AUTO_ACCEPT
    fake_result.output_dir = output_dir
    fake_result.report_json_path = output_dir / "report.json"
    fake_result.summary_csv_path = output_dir / "summary.csv"
    fake_result.report_html_path = output_dir / "report.html"

    class FakeProcessController:
        def __init__(self, **kwargs) -> None:
            self.on_progress = kwargs.get("on_progress")

        def process(self, *args, **kwargs):
            if self.on_progress:
                from app.models.process import ProcessProgress

                self.on_progress(
                    ProcessProgress(stage=ProcessStage.RENDER, completed=1, total=7)
                )
                self.on_progress(
                    ProcessProgress(stage=ProcessStage.REPORT, completed=7, total=7)
                )
            return fake_result

    monkeypatch.setattr("app.cli.ProcessController", FakeProcessController)

    exit_code = main(
        [
            "--config",
            str(config_path),
            "process",
            str(pdf),
            "--output",
            str(output_dir),
            "--student-id",
            "student_001",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Vision model:" in out
    assert "vision-test" in out
    assert "Progress:" in out
    assert "PDF rendering" in out
    assert "Results" in out
    assert "8/10" in out
    assert "Artifacts written to:" in out


def test_cli_process_domain_error(tmp_path: Path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "missing.pdf"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        'ollama:\n  vision_model: "vision-test"\n',
        encoding="utf-8",
    )

    class FailingProcessController:
        def __init__(self, **kwargs) -> None:
            pass

        def process(self, *args, **kwargs):
            raise PdfNotFoundError(pdf)

    monkeypatch.setattr("app.cli.ProcessController", FailingProcessController)

    exit_code = main(
        ["--config", str(config_path), "process", str(pdf)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "Error:" in err
    assert "PDF not found" in err


def test_cli_process_unexpected_error(tmp_path: Path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "answer.pdf"
    pdf.write_bytes(b"%PDF")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        'ollama:\n  vision_model: "vision-test"\n',
        encoding="utf-8",
    )

    class BoomProcessController:
        def __init__(self, **kwargs) -> None:
            pass

        def process(self, *args, **kwargs):
            raise RuntimeError("boom unexpected")

    monkeypatch.setattr("app.cli.ProcessController", BoomProcessController)

    exit_code = main(
        ["--config", str(config_path), "process", str(pdf)]
    )

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Error: boom unexpected" in err


def test_cli_process_requires_vision_model(tmp_path: Path, capsys) -> None:
    pdf = tmp_path / "answer.pdf"
    pdf.write_bytes(b"%PDF")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        'ollama:\n  vision_model: ""\n',
        encoding="utf-8",
    )

    exit_code = main(
        ["--config", str(config_path), "process", str(pdf)]
    )

    assert exit_code == 1
    assert "Vision model is not configured" in capsys.readouterr().err


def test_cli_process_interactive_pdf_choice(tmp_path: Path, monkeypatch, capsys) -> None:
    jawaban = tmp_path / "jawaban"
    jawaban.mkdir()
    pdf_a = jawaban / "alpha.pdf"
    pdf_b = jawaban / "beta.pdf"
    pdf_a.write_bytes(b"%PDF")
    pdf_b.write_bytes(b"%PDF")
    output_dir = tmp_path / "output"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "ollama:",
                '  vision_model: "vision-test"',
                "input:",
                f"  jawaban_dir: {jawaban.as_posix()}",
                "report:",
                f"  output_dir: {output_dir.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    selected: list[Path] = []

    class CapturingProcessController:
        def __init__(self, **kwargs) -> None:
            pass

        def process(self, pdf_path, **kwargs):
            selected.append(Path(pdf_path))
            from app.models.process import ProcessResult
            from app.models.grading import ReviewStatus

            return ProcessResult(
                student_id="student_001",
                questions=[],
                total_score=0.0,
                maximum_total=0.0,
                overall_status=ReviewStatus.AUTO_ACCEPT,
                output_dir=output_dir,
                report_json_path=None,
                summary_csv_path=None,
                report_html_path=None,
                questions_dir=tmp_path / "questions",
                pages_dir=tmp_path / "pages",
                recognition_dir=tmp_path / "recognition",
            )

    monkeypatch.setattr("app.cli.ProcessController", CapturingProcessController)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "2")

    exit_code = main(["--config", str(config_path), "process"])

    assert exit_code == 0
    assert selected == [pdf_b]
    out = capsys.readouterr().out
    assert "PDF tersedia" in out
    assert "beta.pdf" in out
    assert "Memproses:" in out


def test_cli_process_no_pdfs_in_jawaban(tmp_path: Path, capsys) -> None:
    jawaban = tmp_path / "jawaban"
    jawaban.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "ollama:",
                '  vision_model: "vision-test"',
                "input:",
                f"  jawaban_dir: {jawaban.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["--config", str(config_path), "process"])

    assert exit_code == 1
    assert "No PDF files found" in capsys.readouterr().err
