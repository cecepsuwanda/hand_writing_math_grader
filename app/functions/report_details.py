"""Collect per-question report inputs: question.json, grading.json, crop images."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.functions.question_crops import crop_png_path, load_question_crops_items
from app.functions.question_names import grading_filename, question_artifact_filename
from app.functions.regions_artifact import crop_page_number
from app.models.grading import QuestionGrade
from app.models.question import ImageRegionRef, Question
from app.models.question_crops import CropRef, QuestionCrops
from app.models.report import QuestionReportDetail

ModelT = TypeVar("ModelT", bound=BaseModel)


def resolve_crop_name(crops_dir: Path, name: str) -> Path:
    """``page_NNN_region_..png`` → ``<crops_dir>/page_NNN/<name>``."""
    page = crop_page_number(name)
    if page is None:
        return Path(crops_dir) / name
    return crop_png_path(crops_dir, CropRef(page_number=page, name=name))


def _region_crop_path(region: ImageRegionRef, crops_dir: Path | None) -> Path | None:
    raw = (region.crop_path or "").strip()
    if not raw:
        return None
    direct = Path(raw)
    if direct.is_file():
        return direct.resolve()
    name = PureWindowsPath(raw).name
    if crops_dir is not None:
        return resolve_crop_name(crops_dir, name)
    return direct


def _unique(paths: list[Path]) -> list[Path]:
    return list(dict.fromkeys(paths))


def question_crop_paths(
    question: Question,
    mapping_item: QuestionCrops | None,
    crops_dir: Path | None,
) -> list[Path]:
    """Prefer the user-confirmed ``question_crops`` list; else ``image_regions``."""
    if mapping_item is not None and mapping_item.crops and crops_dir is not None:
        return _unique([resolve_crop_name(crops_dir, name) for name in mapping_item.crops])
    candidates = [_region_crop_path(r, crops_dir) for r in question.image_regions]
    return _unique([p for p in candidates if p is not None])


def _load_model(path: Path, model: type[ModelT]) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ValueError(f"invalid artifact {path}: {exc}") from exc


def load_question_report_details(
    questions_dir: Path,
    crops_dir: Path | None,
) -> list[QuestionReportDetail]:
    """One detail per ``question_*/question.json``; ``grading.json`` is optional.

    Raises:
        ValueError: malformed ``question.json``, ``grading.json``, or ``question_crops``.
    """
    questions_dir = Path(questions_dir)
    crops = Path(crops_dir) if crops_dir is not None else None
    mapping = (load_question_crops_items(crops) if crops is not None else None) or {}

    details: list[QuestionReportDetail] = []
    for question_path in sorted(questions_dir.glob(f"*/{question_artifact_filename()}")):
        question = _load_model(question_path, Question)
        grading_path = question_path.parent / grading_filename()
        grade = (
            _load_model(grading_path, QuestionGrade) if grading_path.is_file() else None
        )
        item = mapping.get(question.question_number)
        paths = question_crop_paths(question, item, crops)
        details.append(
            QuestionReportDetail(
                question=question,
                grade=grade,
                stem=item.stem if item is not None else "",
                crop_images=[p for p in paths if p.is_file()],
                missing_crops=[p.name for p in paths if not p.is_file()],
            )
        )
    return sorted(details, key=lambda d: d.question.question_number)
