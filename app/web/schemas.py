"""Request / response contracts and page view-models of the web adapter."""

from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel, Field

from app.exceptions import QuestionCropsInvalidError
from app.models.crop import PageRegions
from app.models.exam_schema import ExamQuestion
from app.models.grading import QuestionGrade
from app.models.question_crops import CropRef, QuestionCropsReport
from app.models.recognition import DetectedRegion, Region, RegionType
from app.models.report import ExamReport
from app.web.files import ReportFile


class TopicOption(BaseModel):
    id: str
    label: str
    active: bool = False
    standard_ready: bool = False


class PdfEntry(BaseModel):
    name: str
    short_name: str
    run_name: str
    has_run: bool = False


class RunSteps(BaseModel):
    """Which artifacts a run folder already holds (drives the stepper)."""

    pages: int = 0
    crops: bool = False
    labels: bool = False
    questions: int = 0
    graded: bool = False
    report: bool = False


class RunSummary(BaseModel):
    name: str
    short_name: str
    student_id: str
    steps: RunSteps
    total_score: float | None = None
    maximum_total: float | None = None
    report_files: list[ReportFile] = Field(default_factory=list)


class DashboardView(BaseModel):
    topics: list[TopicOption]
    active_topic_id: str
    active_topic_label: str
    standard_dir: str
    standard_ready: bool
    kunci_files: list[str]
    pdfs: list[PdfEntry]
    runs: list[RunSummary]
    vision_model: str
    reasoning_model: str
    cloud_models: list[str] = Field(default_factory=list)


class RegionBox(BaseModel):
    """One box from the crop editor, in pixels of the rendered page image."""

    x: float
    y: float
    width: float
    height: float
    type: RegionType = "solution"
    question_number: int = Field(default=0, ge=0)

    def to_detected(self, order: int) -> DetectedRegion:
        return DetectedRegion(
            type=self.type,
            region=Region(x=self.x, y=self.y, width=self.width, height=self.height),
            question_number=self.question_number,
            order=order,
        )


class PageRegionsIn(BaseModel):
    """Boxes in reading order (list position = ``order``)."""

    regions: list[RegionBox] = Field(default_factory=list)


class PageRegionsOut(BaseModel):
    page: PageRegions
    crop_names: list[str] = Field(default_factory=list)


class CropEditorView(BaseModel):
    run: str
    pages: list[PageRegions]
    current: PageRegions
    crop_names: list[str] = Field(default_factory=list)


CROP_LABEL_FIELD_PREFIX = "crop:"
_LABEL_SPLIT_RE = re.compile(r"[\s,;]+")


def parse_crop_labels(form: Mapping[str, str]) -> dict[str, list[int]]:
    """``crop:<crop name>`` → ``"1, 2"`` form fields into crop → question numbers.

    Raises:
        QuestionCropsInvalidError: a token is not a positive integer.
    """
    labels: dict[str, list[int]] = {}
    errors: list[str] = []
    for key, raw in form.items():
        if not key.startswith(CROP_LABEL_FIELD_PREFIX):
            continue
        crop = key.removeprefix(CROP_LABEL_FIELD_PREFIX)
        numbers: list[int] = []
        for token in filter(None, _LABEL_SPLIT_RE.split(raw.strip())):
            if token.isdigit() and int(token) >= 1:
                numbers.append(int(token))
            else:
                errors.append(f"{crop}: {token!r} bukan nomor soal")
        labels[crop] = numbers
    if errors:
        raise QuestionCropsInvalidError(errors)
    return labels


class LabelRow(BaseModel):
    crop: CropRef
    numbers: list[int] = Field(default_factory=list)


class LabelView(BaseModel):
    run: str
    rows: list[LabelRow]
    questions: list[ExamQuestion]
    report: QuestionCropsReport | None = None
    saved: bool = False


class PreviewIn(BaseModel):
    text: str = Field(default="", max_length=2000)


class PreviewOut(BaseModel):
    latex: str | None = None


class QuestionResult(BaseModel):
    question_id: str
    grade: QuestionGrade | None = None


class ResultsView(BaseModel):
    run: str
    report: ExamReport | None
    grades: list[QuestionResult] = Field(default_factory=list)
    report_files: list[ReportFile] = Field(default_factory=list)
