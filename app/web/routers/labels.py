"""Question number per crop: vision detection (job) and manual edit."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from app.web.deps import get_jobs, get_pipeline, is_htmx, job_url, redirect, render, run_url
from app.web.jobs import JobKind, JobManager, JobReporter
from app.web.pipeline import WebPipeline
from app.web.schemas import parse_crop_labels

router = APIRouter()


@router.get("/runs/{run}/labels", response_class=HTMLResponse)
def labels_page(
    request: Request, run: str, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> HTMLResponse:
    return render(request, "labels.html", {"view": pipeline.label_view(run)})


@router.post("/runs/{run}/labels/detect")
def detect_labels(
    request: Request,
    run: str,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> Response:
    name = pipeline.run(run).name

    def task(reporter: JobReporter) -> str:
        pipeline.detect_labels(name, reporter)
        return run_url(name, "/labels")

    job = jobs.submit(run=name, kind=JobKind.LABEL, task=task)
    return redirect(request, job_url(job))


@router.post("/runs/{run}/labels")
async def save_labels(
    request: Request, run: str, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> Response:
    form = await request.form()
    labels = parse_crop_labels(
        {key: value for key, value in form.items() if isinstance(value, str)}
    )
    view = await run_in_threadpool(pipeline.save_labels, run, labels)
    if is_htmx(request):
        return render(request, "partials/label_form.html", {"view": view})
    return redirect(request, run_url(view.run, "/labels"), ok="Nomor soal disimpan")
