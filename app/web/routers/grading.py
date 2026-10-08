"""Recognition + grading jobs, results page, and the JSON result/process API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.models.defaults import DEFAULT_STUDENT_ID
from app.web.deps import get_jobs, get_pipeline, job_url, redirect, render, run_url
from app.web.jobs import JobKind, JobManager, JobReporter
from app.web.pipeline import WebPipeline

router = APIRouter()


def _submit(
    request: Request,
    pipeline: WebPipeline,
    jobs: JobManager,
    run: str,
    kind: JobKind,
    next_suffix: str,
) -> Response:
    name = pipeline.run(run).name
    steps = {
        JobKind.TRANSCRIBE: pipeline.transcribe,
        JobKind.FINISH: pipeline.finish,
        JobKind.FINISH_QUESTIONS: pipeline.finish_questions,
    }

    def task(reporter: JobReporter) -> str:
        steps[kind](name, reporter)
        return run_url(name, next_suffix)

    job = jobs.submit(run=name, kind=kind, task=task)
    return redirect(request, job_url(job))


@router.post("/runs/{run}/transcribe")
def transcribe(
    request: Request,
    run: str,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> Response:
    return _submit(request, pipeline, jobs, run, JobKind.TRANSCRIBE, "/review")


@router.post("/runs/{run}/finish")
def finish(
    request: Request,
    run: str,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> Response:
    return _submit(request, pipeline, jobs, run, JobKind.FINISH, "/results")


@router.post("/runs/{run}/finish-questions")
def finish_questions(
    request: Request,
    run: str,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> Response:
    return _submit(request, pipeline, jobs, run, JobKind.FINISH_QUESTIONS, "/results")


@router.get("/runs/{run}/results", response_class=HTMLResponse)
def results_page(
    request: Request, run: str, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> HTMLResponse:
    return render(request, "results.html", {"view": pipeline.results(run)})


@router.get("/api/results/{question_id}")
def api_result(
    question_id: str, run: str, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> dict[str, Any]:
    path, grade = pipeline.question_grade(run, question_id)
    return {
        "question_id": path.parent.name,
        "grading_path": str(path),
        "grading": grade.model_dump(mode="json"),
    }


class ProcessRequest(BaseModel):
    pdf: str = Field(description="Nama file PDF di jawaban_dir")
    student_id: str | None = Field(
        default=None,
        description=f"Default: NIM dari nama PDF, selain itu {DEFAULT_STUDENT_ID}",
    )


@router.post("/api/process", status_code=202)
def api_process(
    body: ProcessRequest,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> JSONResponse:
    """Whole pipeline without review stops, as a background job."""
    run_name = pipeline.run_name_for_pdf(body.pdf)

    def task(reporter: JobReporter) -> str:
        pipeline.process_pdf(body.pdf, reporter, student_id=body.student_id)
        return run_url(run_name, "/results")

    job = jobs.submit(run=run_name, kind=JobKind.PROCESS, task=task)
    return JSONResponse(
        {"job_id": job.id, "run": run_name, "status_url": f"/api/jobs/{job.id}"},
        status_code=202,
    )
