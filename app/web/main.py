"""FastAPI app factory: state, static files, error mapping, routers."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from app.config import AppConfig, load_config
from app.web.deps import STATIC_DIR, WebState, build_templates
from app.web.errors import install_error_handlers
from app.web.jobs import JobManager
from app.web.pipeline import WebPipeline
from app.web.routers import ROUTERS
from app.web.session import WebSession


class RevalidatedStaticFiles(StaticFiles):
    """Static assets the browser must revalidate (ETag → 304), so app updates are never stale."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    config: AppConfig | None = None,
    *,
    jobs: JobManager | None = None,
    topic_id: str | None = None,
) -> FastAPI:
    config = config if config is not None else load_config()
    session = WebSession(config, topic_id=topic_id)
    job_manager = jobs if jobs is not None else JobManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        job_manager.shutdown()

    app = FastAPI(
        title="Handwriting Math Grader",
        description="UI web lokal untuk menilai jawaban tulisan tangan.",
        lifespan=lifespan,
    )
    app.state.web = WebState(
        session=session,
        pipeline=WebPipeline(session),
        jobs=job_manager,
        templates=build_templates(),
    )
    app.mount("/static", RevalidatedStaticFiles(directory=str(STATIC_DIR)), name="static")
    install_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
