"""HTTP adapters; each module owns one area of the UI."""

from fastapi import APIRouter

from app.web.routers import crops, grading, jobs, kunci, labels, review, runs, topics

ROUTERS: tuple[APIRouter, ...] = (
    topics.router,
    kunci.router,
    runs.router,
    crops.router,
    labels.router,
    review.router,
    grading.router,
    jobs.router,
)
