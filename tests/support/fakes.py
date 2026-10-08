"""Doubles for ports shared across test files (no live Ollama)."""
from __future__ import annotations

import subprocess
from collections.abc import Sequence
from concurrent.futures import Executor, Future
from pathlib import Path

from app.models.process import ProcessProgress, ProcessResult
from app.models.recognition import DetectedRegion, Region
from app.models.validation import StepValidation, ValidationMethod, ValidationStatus
from app.web.jobs import JobManager


class InlineExecutor(Executor):
    """Runs each submitted callable immediately on the caller's thread."""

    def submit(self, fn, /, *args, **kwargs) -> Future:
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 — mirror ThreadPoolExecutor
            future.set_exception(exc)
        return future


class DeferredExecutor(Executor):
    """Holds submitted callables until :meth:`run_all` (a job stays queued until then)."""

    def __init__(self) -> None:
        self.pending: list[tuple] = []

    def submit(self, fn, /, *args, **kwargs) -> Future:
        future: Future = Future()
        self.pending.append((future, fn, args, kwargs))
        return future

    def run_all(self) -> None:
        while self.pending:
            future, fn, args, kwargs = self.pending.pop(0)
            future.set_result(fn(*args, **kwargs))


class FakeJobManager(JobManager):
    """``JobManager`` whose jobs run synchronously inside ``submit`` (no worker thread)."""

    def __init__(self, executor: Executor | None = None) -> None:
        super().__init__(executor=executor or InlineExecutor())


class FakeLatexRunner:
    """``subprocess.run`` double for pdflatex: writes ``<jobname>.pdf/.log/.aux`` in ``cwd``.

    ``returncode != 0`` writes only the log (``log_text``); ``raises`` is thrown instead.
    """

    def __init__(
        self,
        *,
        returncode: int = 0,
        log_text: str = "This is pdfTeX\nOutput written.\n",
        raises: BaseException | None = None,
    ) -> None:
        self.returncode = returncode
        self.log_text = log_text
        self.raises = raises
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, command: list[str], *, cwd: Path, **_kwargs) -> subprocess.CompletedProcess:
        self.calls.append((list(command), Path(cwd)))
        if self.raises is not None:
            raise self.raises
        jobname = next(arg for arg in command if arg.startswith("-jobname=")).split("=", 1)[1]
        folder = Path(cwd)
        (folder / f"{jobname}.log").write_text(self.log_text, encoding="latin-1")
        if self.returncode == 0:
            (folder / f"{jobname}.pdf").write_bytes(b"%PDF-1.5 fake")
            (folder / f"{jobname}.aux").write_text("\\relax", encoding="utf-8")
        return subprocess.CompletedProcess(command, self.returncode)


class FakeProposer:
    """Ink proposer double: returns fixed regions (default one solution box)."""

    def __init__(
        self,
        regions: list[DetectedRegion] | None = None,
        *,
        region: Region | None = None,
        question_number: int = 1,
    ) -> None:
        if regions is None:
            regions = [
                DetectedRegion(
                    type="solution",
                    region=region or Region(x=10, y=10, width=80, height=90),
                    question_number=question_number,
                    order=0,
                )
            ]
        self.regions = regions

    def propose(self, image_path: Path, page_number: int = 1) -> list[DetectedRegion]:
        return list(self.regions)


class FakeClient:
    """Vision/reasoning client double: fixed content or a FIFO queue of responses."""

    def __init__(self, content: str | list[str]) -> None:
        if isinstance(content, list):
            self._queue: list[str] | None = list(content)
            self.content = content[0] if content else ""
        else:
            self._queue = None
            self.content = content
        self.calls: list[tuple[str, Path, str]] = []
        self.text_calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, model: str) -> str:
        self.text_calls.append((prompt, model))
        return self._next()

    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        self.calls.append((prompt, image_path, model))
        return self._next()

    def _next(self) -> str:
        if self._queue is None:
            return self.content
        if not self._queue:
            raise AssertionError("FakeClient exhausted response queue")
        return self._queue.pop(0)


class RecordingJudge:
    """LLM step judge double: fixed verdict, records every call."""

    def __init__(self, response: dict | None = None, *, fail_json: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.response = response or {
            "status": "uncertain",
            "reason": "not enough evidence",
            "confidence": 0.4,
        }
        self.fail_json = fail_json

    def judge_transition(self, **kwargs) -> StepValidation:
        self.calls.append(("transition", kwargs))
        if self.fail_json:
            return StepValidation(
                step_number=kwargs["step_number"],
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.LLM,
                reason="invalid LLM response: bad json",
            )
        return StepValidation(
            step_number=kwargs["step_number"],
            status=ValidationStatus(self.response["status"]),
            method=ValidationMethod.LLM,
            reason=self.response.get("reason", ""),
            confidence=self.response.get("confidence"),
        )

    def judge_final_answer(self, **kwargs) -> StepValidation:
        self.calls.append(("final", kwargs))
        return self.judge_transition(
            step_number=kwargs["step_number"], previous=kwargs.get("last_step"), current=None
        )


class RecordingProcessController:
    """Stands in for ``build_process_controller`` and the controller it returns.

    Patch ``app.services.pipeline_factory.build_process_controller`` with
    :meth:`build`; every builder
    call lands in ``builder_kwargs`` and every run in ``calls`` as
    ``(method, pdf_path | None, kwargs)``.
    """

    def __init__(
        self,
        *,
        error: Exception | None = None,
        progress: Sequence[ProcessProgress] = (),
        result: ProcessResult | None = None,
    ) -> None:
        self.error = error
        self.progress = tuple(progress)
        self.result = result
        self.builder_kwargs: list[dict] = []
        self.calls: list[tuple[str, Path | None, dict]] = []
        self._on_progress = None

    def build(self, config, **kwargs) -> RecordingProcessController:
        self.builder_kwargs.append(kwargs)
        self._on_progress = kwargs.get("on_progress")
        return self

    @property
    def pdf_paths(self) -> list[Path]:
        return [pdf for _method, pdf, _kwargs in self.calls if pdf is not None]

    def process(self, pdf_path, **kwargs) -> ProcessResult:
        self.calls.append(("process", Path(pdf_path), kwargs))
        return self._finish(kwargs)

    def process_from_crops(self, **kwargs) -> ProcessResult:
        self.calls.append(("process_from_crops", None, kwargs))
        return self._finish(kwargs)

    def process_from_questions(self, **kwargs) -> ProcessResult:
        self.calls.append(("process_from_questions", None, kwargs))
        return self._finish(kwargs)

    def transcribe_from_crops(self, **kwargs) -> Path | None:
        self.calls.append(("transcribe_from_crops", None, kwargs))
        if self.error is not None:
            raise self.error
        return kwargs.get("crops_dir")

    def _finish(self, kwargs: dict) -> ProcessResult:
        if self.error is not None:
            raise self.error
        if self._on_progress is not None:
            for event in self.progress:
                self._on_progress(event)
        if self.result is not None:
            return self.result
        return ProcessResult(
            student_id=kwargs.get("student_id") or "student_001",
            output_dir=kwargs["output_dir"],
            questions_dir=kwargs["questions_dir"],
            pages_dir=kwargs["pages_dir"],
            recognition_dir=kwargs["recognition_dir"],
        )
