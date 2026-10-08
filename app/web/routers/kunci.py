"""Kunci jawaban: upload ``.tex`` and ingest it into the active topic's standards."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import Response

from app.web.deps import get_pipeline, redirect
from app.web.pipeline import WebPipeline

router = APIRouter()


@router.post("/kunci/upload")
def upload_kunci(
    request: Request,
    file: UploadFile,
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> Response:
    path = pipeline.upload_kunci(file.filename or "", file.file.read())
    return redirect(request, "/", ok=f"Kunci diunggah: {path.name}")


@router.post("/kunci/ingest")
def ingest_kunci(
    request: Request,
    kunci: Annotated[str, Form()],
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> Response:
    result = pipeline.ingest(kunci)
    return redirect(
        request,
        "/",
        ok=f"{len(result.written)} soal dari {result.source.name} masuk ke {result.standard_dir}",
    )
