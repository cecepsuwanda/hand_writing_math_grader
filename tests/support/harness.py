"""Controller harnesses: wire fakes + a temp workspace, then drive the code under test."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient

from app.config import load_config
from app.controllers.grade_controller import GradeController
from app.controllers.process_controller import ProcessController
from app.functions.run_layout import RunLayout
from app.functions.standards_layout import topic_standard_dir
from app.models.grading import GradeResult, Rubric
from app.models.latex import LatexResult
from app.models.page import RenderResult
from app.models.process import ProcessProgress, ProcessResult, ProcessStage
from app.models.question import ExtractResult, Question
from app.models.recognition import RecognizeResult
from app.models.validation import QuestionValidation, ValidateResult
from app.services.grading.rubric import RubricLoader
from app.services.grading.standard_comparer import StandardFinalComparer
from app.services.grading.step_grader import StepGrader
from app.services.math.llm_judge import LlmStepJudge
from app.services.standards.kunci_ingester import KunciIngester
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.recognizer import OllamaVisionRecognizer
from app.web.jobs import Job, JobManager
from app.web.main import create_app
from tests.support.builders import (
    Q1_KUNCI,
    make_page,
    make_process_question_grade,
    make_report_result,
    sample_rubric,
    write_config,
    write_run_pages,
)
from tests.support.fakes import FakeJobManager, RecordingProcessController

def q1_standard(tmp_path: Path) -> Path:
    """Ingest :data:`Q1_KUNCI` (topic 1.5) into ``tmp_path/standards/topik_1``."""
    kunci = tmp_path / "kunci_q1.tex"
    kunci.write_text(Q1_KUNCI, encoding="utf-8")
    standard = topic_standard_dir(tmp_path / "standards", "1.5")
    KunciIngester(standard).ingest_file(kunci)
    return standard


def make_ollama_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    timeout_seconds: float = 5,
    max_retries: int = 0,
) -> OllamaClient:
    """Real ``OllamaClient`` over ``httpx.MockTransport(handler)`` (no network)."""
    return OllamaClient(
        base_url="http://ollama.test",
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def make_llm_judge(tmp_path: Path, content: str, *, model: str = "reason-test") -> LlmStepJudge:
    """``LlmStepJudge`` whose mocked Ollama always replies with ``content``."""
    prompt = tmp_path / "validation.txt"
    prompt.write_text(
        "prev={{previous_step}}\ncur={{current_step}}\nextra={{extra_context}}", encoding="utf-8"
    )
    client = make_ollama_client(
        lambda _request: httpx.Response(200, json={"message": {"content": content}})
    )
    return LlmStepJudge(client=client, model=model, prompt_path=prompt)


def make_recognizer(
    tmp_path: Path, client=None, *, proposer=None, **kwargs
) -> OllamaVisionRecognizer:
    options = {
        "model": "test-model",
        "output_dir": tmp_path / "recognition",
        "crops_dir": tmp_path / "crops",
    }
    options.update(kwargs)
    if proposer is not None:
        options["proposer"] = proposer
    return OllamaVisionRecognizer(client=client if client is not None else object(), **options)


class WebHarness:
    """Temp ``config.yaml`` + ``create_app`` with a synchronous job manager + ``TestClient``.

    Inputs, runs and standards all live under ``tmp_path``; pipeline builders are
    patched per test (``controller()``) so no page ever reaches Ollama.
    """

    def __init__(self, tmp_path: Path, monkeypatch, *, jobs: JobManager | None = None, **config) -> None:
        self.tmp_path = tmp_path
        self._monkeypatch = monkeypatch
        self.jawaban_dir = tmp_path / "jawaban"
        self.kunci_dir = tmp_path / "kunci"
        self.output_root = tmp_path / "output"
        self.standards_root = tmp_path / "standards"
        for folder in (self.jawaban_dir, self.kunci_dir):
            folder.mkdir(exist_ok=True)
        config.setdefault("jawaban_dir", self.jawaban_dir)
        config.setdefault("kunci_dir", self.kunci_dir)
        config.setdefault("output_root", self.output_root)
        config.setdefault("standards_root", self.standards_root)
        self.config = load_config(write_config(tmp_path, **config))
        self.jobs = jobs or FakeJobManager()
        self.app = create_app(self.config, jobs=self.jobs)
        self.client = TestClient(self.app, follow_redirects=False)
        self.fake: RecordingProcessController | None = None

    def pdf(self, name: str = "answer.pdf") -> Path:
        path = self.jawaban_dir / name
        path.write_bytes(b"%PDF-1.4 test")
        return path

    def kunci(self, name: str = "kunci.tex", text: str = Q1_KUNCI) -> Path:
        path = self.kunci_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def standard(self) -> Path:
        """Ingest :data:`Q1_KUNCI` into this harness's topic 1.5 standard."""
        return q1_standard(self.tmp_path)

    def run_dir(self, name: str = "answer", *page_sizes: tuple[int, int]) -> RunLayout:
        """Run folder with rendered blank pages (one 200x300 page by default)."""
        layout = RunLayout(root=self.output_root / name)
        write_run_pages(layout.pages_dir, *page_sizes)
        return layout

    def controller(self, **kwargs) -> RecordingProcessController:
        self.fake = RecordingProcessController(**kwargs)
        self._monkeypatch.setattr(
            "app.services.pipeline_factory.build_process_controller", self.fake.build
        )
        return self.fake

    def htmx(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = {"HX-Request": "true", **kwargs.pop("headers", {})}
        return self.client.request(method, url, headers=headers, **kwargs)

    def job(self, response: httpx.Response) -> Job:
        """The job a 303 / ``HX-Redirect`` response points at."""
        location = response.headers.get("HX-Redirect") or response.headers["location"]
        assert location.startswith("/jobs/"), location
        return self.jobs.get(location.removeprefix("/jobs/"))


class ProcessHarness:
    """``ProcessController`` wired to seven ``MagicMock`` stages with canned results."""

    def __init__(self, tmp_path: Path) -> None:
        # Mirrors RunLayout: artifact dirs live inside the run root (= workspace_root).
        self.output_dir = tmp_path / "output"
        self.pages_dir = self.output_dir / "pages"
        self.recognition_dir = self.output_dir / "recognition"
        self.questions_dir = self.output_dir / "questions"
        self.crops_dir = self.output_dir / "crops"
        self.pdf = tmp_path / "answer.pdf"
        self.pdf.write_bytes(b"%PDF")
        self.progress: list[ProcessStage] = []
        self.progress_events: list[ProcessProgress] = []
        self.cleared: list[tuple[Path, list[str]]] = []
        self.controller_options: dict = {}

        self.render = MagicMock()
        self.render.render.return_value = RenderResult(
            pages=[make_page()],
            output_dir=self.pages_dir,
            metadata_path=self.pages_dir / "pages.json",
        )
        self.recognize = MagicMock()
        self.recognize.recognize_pages.return_value = RecognizeResult(
            pages=[], output_dir=self.recognition_dir, artifact_paths=[]
        )
        self.extract = MagicMock()
        self.extract.extract.return_value = ExtractResult(
            questions=[], output_dir=self.questions_dir, artifact_paths=[]
        )
        self.latex = MagicMock()
        self.latex.build.return_value = LatexResult(artifacts=[], questions_dir=self.questions_dir)
        self.validate = MagicMock()
        self.validate.validate.return_value = ValidateResult(
            validations=[], questions_dir=self.questions_dir, artifact_paths=[]
        )
        self.grade = MagicMock()
        self.grade.grade.return_value = GradeResult(
            grades=[make_process_question_grade()],
            questions_dir=self.questions_dir,
            standard_dir=tmp_path / "standards",
            artifact_paths=[],
        )
        self.report = MagicMock()
        self.report.report.return_value = make_report_result(tmp_path)

    @property
    def stage_calls(self) -> list[MagicMock]:
        """The mocked entry point of each stage, in pipeline order."""
        return [
            self.render.render,
            self.recognize.recognize_pages,
            self.extract.extract,
            self.latex.build,
            self.validate.validate,
            self.grade.grade,
            self.report.report,
        ]

    def controller(self) -> ProcessController:
        return ProcessController(
            render_controller=self.render,
            recognize_controller=self.recognize,
            extract_controller=self.extract,
            latex_controller=self.latex,
            validate_controller=self.validate,
            grade_controller=self.grade,
            report_controller=self.report,
            on_progress=self._record_progress,
            on_output_cleared=lambda root, names: self.cleared.append((root, names)),
            **self.controller_options,
        )

    def _record_progress(self, progress: ProcessProgress) -> None:
        self.progress.append(progress.stage)
        self.progress_events.append(progress)

    def process(self, **overrides) -> ProcessResult:
        kwargs = {
            "pages_dir": self.pages_dir,
            "recognition_dir": self.recognition_dir,
            "questions_dir": self.questions_dir,
            "output_dir": self.output_dir,
            "dpi": 200,
            "workspace_root": self.output_dir,
        }
        kwargs.update(overrides)
        return self.controller().process(self.pdf, **kwargs)

    def process_from_crops(self, **overrides) -> ProcessResult:
        kwargs = {
            "pages_dir": self.pages_dir,
            "recognition_dir": self.recognition_dir,
            "questions_dir": self.questions_dir,
            "output_dir": self.output_dir,
            "crops_dir": self.crops_dir,
        }
        kwargs.update(overrides)
        return self.controller().process_from_crops(**kwargs)

    def transcribe_from_crops(self, **overrides) -> Path | None:
        kwargs = {
            "pages_dir": self.pages_dir,
            "recognition_dir": self.recognition_dir,
            "questions_dir": self.questions_dir,
            "crops_dir": self.crops_dir,
        }
        kwargs.update(overrides)
        return self.controller().transcribe_from_crops(**kwargs)

    def process_from_questions(self, **overrides) -> ProcessResult:
        kwargs = {
            "questions_dir": self.questions_dir,
            "output_dir": self.output_dir,
            "pages_dir": self.pages_dir,
            "recognition_dir": self.recognition_dir,
            "crops_dir": self.crops_dir,
        }
        kwargs.update(overrides)
        return self.controller().process_from_questions(**kwargs)


class GradingWorkspace:
    """Temp standard (rubric, optional solution) + questions tree for the grade stage."""

    def __init__(self, tmp_path: Path, rubric: Rubric | None = None) -> None:
        self.standard = topic_standard_dir(tmp_path / "standards", "1.5")
        self.questions_dir = tmp_path / "questions"
        self.add_rubric(rubric or sample_rubric())

    def add_rubric(self, rubric: Rubric, number: int = 1) -> Path:
        path = self.standard / "rubrics" / f"question_{number:03d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rubric.model_dump_json(indent=2), encoding="utf-8")
        return path

    def add_solution(self, tex: str = "% final answer\nx < 4\n", number: int = 1) -> Path:
        path = self.standard / "solutions" / f"question_{number:03d}.tex"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tex, encoding="utf-8")
        return path

    def add_question(
        self, question: Question, validation: QuestionValidation | None = None
    ) -> Path:
        """Write ``question.json`` (+ ``validation.json``); returns the question path."""
        qdir = self.questions_dir / question.question_id
        qdir.mkdir(parents=True, exist_ok=True)
        qpath = qdir / "question.json"
        qpath.write_text(question.model_dump_json(indent=2), encoding="utf-8")
        if validation is not None:
            (qdir / "validation.json").write_text(
                validation.model_dump_json(indent=2), encoding="utf-8"
            )
        return qpath

    def grade(
        self,
        *,
        with_comparer: bool = False,
        role_rubric_parts: Mapping[str, Sequence[str]] | None = None,
    ) -> GradeResult:
        comparer = StandardFinalComparer(self.standard) if with_comparer else None
        grader = StepGrader(
            RubricLoader(self.standard),
            standard_comparer=comparer,
            role_rubric_parts=role_rubric_parts,
        )
        return GradeController(grader, self.standard).grade(self.questions_dir)
