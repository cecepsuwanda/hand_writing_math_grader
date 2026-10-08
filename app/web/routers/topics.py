"""Dashboard (home) and active topic selection."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from app.web.deps import get_jobs, get_pipeline, redirect, render
from app.web.jobs import JobManager
from app.web.pipeline import WebPipeline

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> HTMLResponse:
    view = pipeline.dashboard()
    run_jobs = {run.name: jobs.latest_for(run.name) for run in view.runs}
    return render(request, "dashboard.html", {"view": view, "run_jobs": run_jobs})


@router.post("/topic")
def select_topic(
    request: Request,
    topic_id: Annotated[str, Form()],
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> Response:
    pack = pipeline.select_topic(topic_id)
    return redirect(request, "/", ok=f"Topik aktif: {pack.id} — {pack.label}")
