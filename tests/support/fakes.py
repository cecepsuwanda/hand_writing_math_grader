"""Doubles for ports shared across test files (no live Ollama)."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.functions.run_layout import RunLayout
from app.models.process import ProcessProgress, ProcessResult
from app.models.recognition import DetectedRegion, Region
from app.models.validation import StepValidation, ValidationMethod, ValidationStatus


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


class RecordingMenuActions:
    """:class:`MenuActions` double: records ``(action, args)``; ``errors`` makes an action raise."""

    def __init__(
        self,
        *,
        run_root: Path,
        pdf: Path | None = None,
        topic_id: str = "2",
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.run_root = run_root
        self.pdf = pdf or run_root.parent / "answer.pdf"
        self.topic_id = topic_id
        self.errors = dict(errors or {})
        self.calls: list[tuple[str, tuple]] = []

    @property
    def names(self) -> list[str]:
        return [name for name, _args in self.calls]

    def _record(self, name: str, *args) -> None:
        self.calls.append((name, args))
        if name in self.errors:
            raise self.errors[name]

    def select_topic(self, active_topic_id: str) -> str:
        self._record("select_topic", active_topic_id)
        return self.topic_id

    def select_pdf(self, config) -> Path:
        self._record("select_pdf")
        return self.pdf

    def pick_run(self, config) -> RunLayout:
        self._record("pick_run")
        return RunLayout(root=self.run_root)

    def ingest(self, config, topic_id: str) -> None:
        self._record("ingest", topic_id)

    def propose_crops(self, config, layout: RunLayout, pdf_path: Path) -> None:
        self._record("propose_crops", layout, pdf_path)

    def recrop(self, config, layout: RunLayout) -> None:
        self._record("recrop", layout)

    def label(self, config, layout: RunLayout, mode) -> None:
        self._record("label", layout, mode)

    def finish(self, config, layout: RunLayout, topic_id: str | None) -> None:
        self._record("finish", layout, topic_id)


class RecordingProcessController:
    """Stands in for ``build_process_controller`` and the controller it returns.

    Patch ``app.cli.build_process_controller`` with :meth:`build`; every builder
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
