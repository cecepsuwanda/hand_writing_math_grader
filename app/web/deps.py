"""Shared request plumbing: app state, template rendering, redirects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.functions.paths import shorten_pdf_name
from app.web.jobs import Job, JobManager
from app.web.pipeline import WebPipeline
from app.web.session import WebSession

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


@dataclass(frozen=True)
class WebState:
    session: WebSession
    pipeline: WebPipeline
    jobs: JobManager
    templates: Jinja2Templates


def build_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["urlq"] = url_segment
    templates.env.filters["short_pdf"] = lambda name: shorten_pdf_name(Path(name))
    templates.env.globals["run_url"] = run_url
    templates.env.globals["static_url"] = static_url
    return templates


def static_url(path: str) -> str:
    """URL of a bundled asset, versioned by mtime so browsers drop stale copies after updates."""
    version = (STATIC_DIR / path).stat().st_mtime_ns
    return f"/static/{path}?v={version}"


def get_state(request: Request) -> WebState:
    return request.app.state.web


def get_pipeline(request: Request) -> WebPipeline:
    return get_state(request).pipeline


def get_jobs(request: Request) -> JobManager:
    return get_state(request).jobs


def url_segment(value: object) -> str:
    """Percent-encode one path segment (run names contain spaces)."""
    return quote(str(value), safe="")


def run_url(run: str, suffix: str = "") -> str:
    return f"/runs/{url_segment(run)}{suffix}"


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def render(
    request: Request,
    template: str,
    context: dict | None = None,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    state = get_state(request)
    full = {"active_topic": state.session.pack, **(context or {})}
    return state.templates.TemplateResponse(
        request, template, full, status_code=status_code, headers=headers
    )


def redirect(request: Request, url: str, *, ok: str | None = None) -> Response:
    """303 for plain forms; ``HX-Redirect`` so HTMX navigates instead of swapping."""
    if ok:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode({'ok': ok})}"
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def job_url(job: Job) -> str:
    return f"/jobs/{job.id}"
