"""Background jobs for long pipeline steps, with an event log streamed over SSE."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.exceptions import JobAlreadyRunningError, JobNotFoundError, MathGraderError
from app.models.process import ProcessProgress

logger = logging.getLogger(__name__)


class JobKind(StrEnum):
    PROPOSE_CROPS = "propose_crops"
    LABEL = "label"
    TRANSCRIBE = "transcribe"
    FINISH = "finish"
    FINISH_QUESTIONS = "finish_questions"
    PROCESS = "process"


JOB_TITLES: dict[JobKind, str] = {
    JobKind.PROPOSE_CROPS: "Render PDF + usulan kotak crop",
    JobKind.LABEL: "Deteksi nomor soal (vision)",
    JobKind.TRANSCRIBE: "Transkripsi crop → question.json",
    JobKind.FINISH: "Transkripsi + penilaian",
    JobKind.FINISH_QUESTIONS: "Penilaian dari question.json",
    JobKind.PROCESS: "Proses penuh tanpa review",
}


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobEvent(BaseModel):
    seq: int
    message: str
    completed: int | None = None
    total: int | None = None


class Job(BaseModel):
    id: str
    run: str
    kind: JobKind
    status: JobStatus = JobStatus.QUEUED
    events: list[JobEvent] = Field(default_factory=list)
    error: str = ""
    # Page to continue on once the job is done (set by the task).
    next_url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def title(self) -> str:
        return JOB_TITLES[self.kind]

    @property
    def finished(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED)

    @property
    def last_progress(self) -> JobEvent | None:
        return next((e for e in reversed(self.events) if e.total), None)


class JobReporter:
    """Handed to a task; turns pipeline callbacks into job events."""

    def __init__(self, manager: JobManager, job_id: str) -> None:
        self._manager = manager
        self._job_id = job_id

    def message(self, text: str) -> None:
        self._manager._append(self._job_id, text)

    def progress(self, progress: ProcessProgress) -> None:
        self._manager._append(
            self._job_id,
            progress.stage.value,
            completed=progress.completed,
            total=progress.total,
        )


JobTask = Callable[[JobReporter], str]


class JobManager:
    """One worker thread: local Ollama and the per-run folders cannot take parallel runs."""

    def __init__(self, executor: Executor | None = None) -> None:
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="grader-job"
        )
        self._jobs: dict[str, Job] = {}
        self._changed = threading.Condition()

    def submit(self, *, run: str, kind: JobKind, task: JobTask) -> Job:
        """Queue ``task``; it returns the URL to continue on.

        Raises:
            JobAlreadyRunningError: ``run`` already has a queued or running job.
        """
        with self._changed:
            active = self._active_for(run)
            if active is not None:
                raise JobAlreadyRunningError(run, active.id)
            job = Job(id=uuid.uuid4().hex[:12], run=run, kind=kind)
            self._jobs[job.id] = job
        self._executor.submit(self._execute, job.id, task)
        return self.get(job.id)

    def get(self, job_id: str) -> Job:
        with self._changed:
            return self._require(job_id).model_copy(deep=True)

    def latest_for(self, run: str) -> Job | None:
        with self._changed:
            jobs = [j for j in self._jobs.values() if j.run == run]
            if not jobs:
                return None
            return max(jobs, key=lambda j: j.created_at).model_copy(deep=True)

    def wait(self, job_id: str, *, after_seq: int, timeout: float) -> Job:
        """Block until ``job_id`` has an event newer than ``after_seq``, finishes, or times out."""
        with self._changed:
            self._changed.wait_for(
                lambda: self._has_news(job_id, after_seq), timeout=timeout
            )
            return self._require(job_id).model_copy(deep=True)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, job_id: str, task: JobTask) -> None:
        self._update(job_id, status=JobStatus.RUNNING)
        try:
            next_url = task(JobReporter(self, job_id))
        except MathGraderError as exc:
            self._update(job_id, status=JobStatus.FAILED, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — a crashed job must still report failure
            logger.exception("Unexpected error in job %s", job_id)
            self._update(
                job_id, status=JobStatus.FAILED, error=f"Error tak terduga: {exc}"
            )
        else:
            self._update(job_id, status=JobStatus.DONE, next_url=next_url)

    def _append(
        self,
        job_id: str,
        message: str,
        *,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        with self._changed:
            job = self._require(job_id)
            job.events.append(
                JobEvent(
                    seq=len(job.events), message=message, completed=completed, total=total
                )
            )
            self._changed.notify_all()

    def _update(self, job_id: str, **changes: object) -> None:
        with self._changed:
            job = self._require(job_id)
            for name, value in changes.items():
                setattr(job, name, value)
            self._changed.notify_all()

    def _require(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def _active_for(self, run: str) -> Job | None:
        return next(
            (j for j in self._jobs.values() if j.run == run and not j.finished), None
        )

    def _has_news(self, job_id: str, after_seq: int) -> bool:
        job = self._jobs.get(job_id)
        return job is None or job.finished or len(job.events) - 1 > after_seq
