"""Map domain errors to HTTP: JSON for ``/api``, a flash for HTMX, a page otherwise."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.exceptions import (
    ArtifactNotFoundError,
    JobAlreadyRunningError,
    JobNotFoundError,
    KunciNotFoundError,
    MathGraderError,
    PdfNotFoundError,
    RunNotFoundError,
    UnknownTopicError,
    UnsafeArtifactPathError,
    UploadRejectedError,
)
from app.web.deps import is_htmx, render

logger = logging.getLogger(__name__)

_STATUS: dict[type[MathGraderError], int] = {
    RunNotFoundError: 404,
    ArtifactNotFoundError: 404,
    JobNotFoundError: 404,
    PdfNotFoundError: 404,
    KunciNotFoundError: 404,
    UnsafeArtifactPathError: 400,
    UploadRejectedError: 400,
    UnknownTopicError: 400,
    JobAlreadyRunningError: 409,
}
DEFAULT_ERROR_STATUS = 422


def status_for(exc: MathGraderError) -> int:
    for cls in type(exc).__mro__:
        if cls in _STATUS:
            return _STATUS[cls]
    return DEFAULT_ERROR_STATUS


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(MathGraderError)
    async def _domain_error(request: Request, exc: MathGraderError) -> Response:
        return _error_response(request, str(exc), status_for(exc))

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, exc: RequestValidationError) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": jsonable_encoder(exc.errors())}, status_code=422)
        detail = "; ".join(
            f"{'.'.join(str(p) for p in error['loc'][1:]) or 'input'}: {error['msg']}"
            for error in exc.errors()
        )
        return _error_response(request, f"Input tidak valid: {detail}", 422)


def _error_response(request: Request, message: str, status: int) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=status)
    if is_htmx(request):
        return render(
            request,
            "partials/flash.html",
            {"level": "error", "message": message},
            status_code=status,
            headers={"HX-Retarget": "#flash", "HX-Reswap": "innerHTML"},
        )
    return render(request, "error.html", {"message": message, "status": status}, status_code=status)
