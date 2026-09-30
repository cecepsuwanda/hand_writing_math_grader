"""Thin FastAPI adapter over existing MVC controllers (pasca-MVP).

CLI remains the required entry point. This module does not own grading logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import load_config
from app.exceptions import MathGraderError
from app.functions.grading_artifact import load_question_grade
from app.functions.paths import resolve_jawaban_pdf
from app.functions.question_names import grading_filename, parse_question_ref
from app.functions.run_layout import build_run_layout, layout_for_pdf, resolve_run_name
from app.models.defaults import DEFAULT_STUDENT_ID
from app.services.pipeline_factory import build_process_controller

try:
    from fastapi import FastAPI, HTTPException
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fastapi is required for the API adapter; pip install fastapi uvicorn"
    ) from exc

app = FastAPI(
    title="Handwriting Math Grader API",
    description="Thin HTTP adapter; engine logic stays in CLI controllers/services.",
)


class ProcessRequest(BaseModel):
    pdf: str = Field(description="PDF path or name under jawaban_dir")
    student_id: str = DEFAULT_STUDENT_ID


class HealthResponse(BaseModel):
    status: str = "ok"


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/process")
def api_process(body: ProcessRequest) -> dict[str, Any]:
    config = load_config()
    try:
        pdf_path = resolve_jawaban_pdf(Path(body.pdf), config.input.jawaban_dir)
    except (MathGraderError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF not found: {pdf_path}")

    layout = layout_for_pdf(config.output.root_dir, pdf_path)
    controller = build_process_controller(
        config,
        recognition_dir=layout.recognition_dir,
        crops_dir=layout.crops_dir,
    )
    try:
        result = controller.process(
            pdf_path,
            pages_dir=layout.pages_dir,
            recognition_dir=layout.recognition_dir,
            questions_dir=layout.questions_dir,
            output_dir=layout.report_dir,
            dpi=config.pdf.dpi,
            student_id=body.student_id,
            workspace_root=layout.root,
            reset_workspace=True,
            crops_dir=layout.crops_dir,
            # HTTP has no stdin: never block on the crop confirm prompt.
            force_yes=True,
        )
    except MathGraderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "run": layout.name,
        "student_id": result.student_id,
        "total_score": result.total_score,
        "maximum_total": result.maximum_total,
        "overall_status": result.overall_status.value,
        "questions": [q.model_dump(mode="json") for q in result.questions],
        "output_dir": str(result.output_dir),
        "questions_dir": str(result.questions_dir),
        "report_json_path": (
            str(result.report_json_path) if result.report_json_path else None
        ),
    }


@app.get("/api/results/{question_id}")
def api_results(question_id: str, run: str) -> dict[str, Any]:
    config = load_config()
    questions_dir = build_run_layout(
        config.output.root_dir, resolve_run_name(run)
    ).questions_dir
    qdir = questions_dir / question_id
    if not qdir.is_dir():
        try:
            qdir = questions_dir / parse_question_ref(question_id)
        except ValueError:
            pass
    grading_path = qdir / grading_filename()
    if not grading_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"grading artifact not found for {question_id}",
        )
    try:
        grading = load_question_grade(grading_path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "question_id": qdir.name,
        "grading_path": str(grading_path),
        "grading": grading.model_dump(mode="json"),
    }


def main() -> None:
    import uvicorn

    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
