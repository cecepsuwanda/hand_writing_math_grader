"""Transcription review: edit question.json steps with a SymPy/KaTeX preview."""

from __future__ import annotations

from typing import Annotated, Any, get_args

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import HTMLResponse

from app.models.question_review import QuestionReviewResult
from app.models.recognition import SymbolicKind
from app.web.deps import get_pipeline, render
from app.web.pipeline import WebPipeline
from app.web.schemas import PreviewIn, PreviewOut

router = APIRouter()


@router.get("/runs/{run}/review", response_class=HTMLResponse)
def review_page(
    request: Request, run: str, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]
) -> HTMLResponse:
    layout = pipeline.run(run)
    return render(
        request,
        "review.html",
        {
            "run": layout.name,
            "review": pipeline.review(layout.name),
            "symbolic_kinds": list(get_args(SymbolicKind)),
        },
    )


@router.put("/api/runs/{run}/questions/{question_id}")
def save_question(
    run: str,
    question_id: str,
    payload: Annotated[dict[str, Any], Body()],
    pipeline: Annotated[WebPipeline, Depends(get_pipeline)],
) -> QuestionReviewResult:
    payload["question_id"] = question_id
    return pipeline.save_question(run, payload)


@router.post("/api/preview")
def preview(body: PreviewIn, pipeline: Annotated[WebPipeline, Depends(get_pipeline)]) -> PreviewOut:
    return pipeline.preview(body.text)
