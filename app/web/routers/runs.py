"""Student PDFs, run overview, and read-only run artifacts (images, reports)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.web import files
from app.web.deps import get_jobs, get_pipeline, job_url, redirect, render, run_url
from app.web.files import ReportFile
from app.web.jobs import JobKind, JobManager, JobReporter
from app.web.pipeline import WebPipeline

router = APIRouter()

_MEDIA_TYPES: dict[ReportFile, str] = {
    ReportFile.PDF: "application/pdf",
    ReportFile.TEX: "text/plain; charset=utf-8",
    ReportFile.HTML: "text/html; charset=utf-8",
    ReportFile.JSON: "application/json",
    ReportFile.CSV: "text/csv; charset=utf-8",
}


@router.post("/pdfs/upload")
def upload_pdf(
    request: Request,
    file: UploadFile,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> Response:
    path = pipeline.upload_pdf(file.filename or "", file.file.read())
    return redirect(request, "/", ok=f"PDF diunggah: {path.name}")


@router.post("/pdfs/propose")
def propose_crops(
    request: Request,
    pdf: Annotated[str, Form()],
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> Response:
    run_name = pipeline.run_name_for_pdf(pdf)

    def task(reporter: JobReporter) -> str:
        layout = pipeline.propose_crops(pdf, reporter)
        return run_url(layout.name, "/crops")

    job = jobs.submit(run=run_name, kind=JobKind.PROPOSE_CROPS, task=task)
    return redirect(request, job_url(job))


@router.get("/runs/{run}", response_class=HTMLResponse)
def run_overview(
    request: Request,
    run: str,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> HTMLResponse:
    summary = pipeline.run_summary(run)
    return render(
        request, "run.html", {"run": summary, "job": jobs.latest_for(summary.name)}
    )


@router.get("/runs/{run}/pages/{page_number}/image")
def page_image(
    run: str, page_number: int, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> FileResponse:
    path = files.page_image_path(pipeline.run(run), page_number)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})


@router.get("/runs/{run}/crops/{crop_name}")
def crop_image(
    run: str, crop_name: str, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> FileResponse:
    path = files.crop_image_path(pipeline.run(run), crop_name)
    # Recrop rewrites the same file name; never let the browser show a stale box.
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/runs/{run}/files/{kind}")
def report_file(
    run: str, kind: ReportFile, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> FileResponse:
    layout = pipeline.run(run)
    path = files.report_file_path(layout, kind)
    inline = kind in (ReportFile.PDF, ReportFile.HTML)
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[kind],
        filename=f"{layout.name}_{path.name}",
        content_disposition_type="inline" if inline else "attachment",
    )
