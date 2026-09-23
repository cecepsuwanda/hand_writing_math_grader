"""Thin FastAPI adapter over existing MVC controllers (pasca-MVP).

CLI remains the required entry point. This module does not own grading logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import load_config
from app.functions.paths import resolve_jawaban_pdf
from app.functions.question_names import grading_filename, question_dir_name
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
    student_id: str = "student_001"


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
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF not found: {pdf_path}")

    controller = build_process_controller(config)
    result = controller.process(
        pdf_path,
        pages_dir=config.pdf.output_dir,
        recognition_dir=config.recognition.output_dir,
        questions_dir=config.questions.output_dir,
        output_dir=config.report.output_dir,
        dpi=config.pdf.dpi,
        student_id=body.student_id,
        workspace_root=config.report.output_dir,
        reset_workspace=True,
        crops_dir=config.recognition.crops_dir,
    )
    return {
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
def api_results(question_id: str) -> dict[str, Any]:
    config = load_config()
    qdir = config.questions.output_dir / question_id
    if not qdir.is_dir():
        try:
            number = int(question_id.replace("question_", ""))
            qdir = config.questions.output_dir / question_dir_name(number)
        except ValueError:
            pass
    grading_path = qdir / grading_filename()
    if not grading_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"grading artifact not found for {question_id}",
        )
    try:
        grading = json.loads(grading_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"invalid grading JSON for {question_id}: {exc}",
        ) from exc
    return {
        "question_id": qdir.name,
        "grading_path": str(grading_path),
        "grading": grading,
    }


def main() -> None:
    import uvicorn

    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
