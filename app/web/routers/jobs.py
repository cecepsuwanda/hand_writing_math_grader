"""Job page, its SSE progress stream, and a JSON status endpoint."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.functions.sse import SSE_KEEPALIVE, format_sse
from app.web.deps import get_jobs, get_state, render
from app.web.jobs import Job, JobManager

router = APIRouter()

SSE_WAIT_SECONDS = 10.0


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(
    request: Request, job_id: str, jobs: Annotated[JobManager, Depends(get_jobs)]
) -> HTMLResponse:
    return render(request, "job.html", {"job": jobs.get(job_id)})


@router.get("/jobs/{job_id}/events")
def job_events(
    request: Request, job_id: str, jobs: Annotated[JobManager, Depends(get_jobs)]
) -> StreamingResponse:
    jobs.get(job_id)
    templates = get_state(request).templates

    def partial(name: str, job: Job) -> str:
        return templates.get_template(name).render(job=job)

    def stream() -> Iterator[str]:
        seen = -1
        while True:
            job = jobs.wait(job_id, after_seq=seen, timeout=SSE_WAIT_SECONDS)
            fresh = [event for event in job.events if event.seq > seen]
            if fresh:
                seen = fresh[-1].seq
                yield format_sse("progress", partial("partials/job_progress.html", job))
            if job.finished:
                yield format_sse("done", partial("partials/job_done.html", job))
                return
            if not fresh:
                yield SSE_KEEPALIVE

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/jobs/{job_id}")
def job_status(job_id: str, jobs: Annotated[JobManager, Depends(get_jobs)]) -> Job:
    return jobs.get(job_id)
