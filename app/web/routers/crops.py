"""Manual crop editor: draw boxes on the page image, save, recrop."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from app.web.deps import get_pipeline, render
from app.web.pipeline import WebPipeline
from app.web.schemas import PageRegionsIn, PageRegionsOut

router = APIRouter()


@router.get("/runs/{run}/crops", response_class=HTMLResponse)
def crop_editor(
    request: Request,
    run: str,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
    page: Annotated[int | None, Query(ge=1)] = None,
) -> HTMLResponse:
    return render(request, "crops.html", {"view": pipeline.crop_editor(run, page)})


@router.get("/runs/{run}/pages/{page_number}/thumbs", response_class=HTMLResponse)
def crop_thumbs(
    request: Request,
    run: str,
    page_number: int,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> HTMLResponse:
    out = pipeline.page_regions(run, page_number)
    return render(request, "partials/crop_thumbs.html", {"run": run, "out": out})


@router.get("/api/runs/{run}/pages/{page_number}/regions")
def get_regions(
    run: str, page_number: int, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> PageRegionsOut:
    return pipeline.page_regions(run, page_number)


@router.put("/api/runs/{run}/pages/{page_number}/regions")
def put_regions(
    run: str,
    page_number: int,
    body: PageRegionsIn,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> PageRegionsOut:
    return pipeline.save_page_regions(run, page_number, body)
