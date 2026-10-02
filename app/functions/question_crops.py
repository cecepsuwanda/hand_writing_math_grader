"""Question → crop mapping: assignment, persistence, validation (FP + small I/O)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from app.functions.question_names import question_dir_name
from app.functions.regions_artifact import (
    crop_filename,
    load_regions_artifact,
    regions_json_path,
)
from app.models.question_crops import (
    CropRef,
    QuestionCropMap,
    QuestionCrops,
    QuestionCropsReport,
)

QUESTION_CROPS_DIRNAME = "question_crops"


def question_crops_dir(crops_dir: Path) -> Path:
    return Path(crops_dir) / QUESTION_CROPS_DIRNAME


def question_crops_path(crops_dir: Path, question_number: int) -> Path:
    return question_crops_dir(crops_dir) / f"{question_dir_name(question_number)}.json"


def crop_png_path(crops_dir: Path, crop: CropRef) -> Path:
    return Path(crops_dir) / f"page_{crop.page_number:03d}" / crop.name


def list_crops_in_reading_order(crops_dir: Path) -> list[CropRef]:
    """All crops listed in ``page_*/page_*_regions.json``, by page then order."""
    crops_dir = Path(crops_dir)
    if not crops_dir.is_dir():
        return []
    refs: list[CropRef] = []
    for page_dir in crops_dir.glob("page_*"):
        if not page_dir.is_dir():
            continue
        try:
            page_number = int(page_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if page_number < 1:
            continue
        json_path = regions_json_path(page_dir, page_number)
        if not json_path.is_file():
            continue
        _page, _source, regions = load_regions_artifact(json_path)
        for index, region in enumerate(regions):
            refs.append(
                CropRef(
                    page_number=page_number,
                    order=region.order,
                    name=crop_filename(page_number, index),
                )
            )
    return sorted(refs, key=lambda r: (r.page_number, r.order, r.name))


def _empty_map(numbers: Iterable[int]) -> QuestionCropMap:
    return {n: [] for n in sorted(set(numbers))}


def assign_by_labels(
    crops: list[CropRef],
    labels: Mapping[str, list[int]],
    numbers: list[int],
) -> QuestionCropMap:
    """Labeled crops start their question(s); unlabeled crops continue the previous one."""
    allowed = set(numbers)
    mapping = _empty_map(numbers)
    current: int | None = None
    for crop in crops:
        found: list[int] = []
        for number in labels.get(crop.name, []):
            if number in allowed and number not in found:
                found.append(number)
        if found:
            for number in found:
                mapping[number].append(crop.name)
            current = found[-1]
        elif current is not None:
            mapping[current].append(crop.name)
    return mapping


def assign_sequential(crops: list[CropRef], numbers: list[int]) -> QuestionCropMap:
    """One crop per question in reading order, only when the counts match."""
    ordered = sorted(set(numbers))
    mapping = _empty_map(ordered)
    if len(crops) != len(ordered):
        return mapping
    for number, crop in zip(ordered, crops):
        mapping[number].append(crop.name)
    return mapping


def crop_to_questions(mapping: Mapping[int, list[str]]) -> dict[str, list[int]]:
    """Inverse map: crop file name → question numbers (ascending)."""
    inverse: dict[str, list[int]] = {}
    for number in sorted(mapping):
        for name in mapping[number]:
            numbers = inverse.setdefault(name, [])
            if number not in numbers:
                numbers.append(number)
    return inverse


def write_question_crops(
    crops_dir: Path,
    mapping: Mapping[int, list[str]],
    *,
    stems: Mapping[int, str] | None = None,
) -> list[Path]:
    """Write one ``question_NNN.json`` per number; drop stale files first."""
    target = question_crops_dir(crops_dir)
    target.mkdir(parents=True, exist_ok=True)
    for stale in target.glob("question_*.json"):
        stale.unlink(missing_ok=True)
    stems = stems or {}
    paths: list[Path] = []
    for number in sorted(mapping):
        payload = QuestionCrops(
            question_number=number,
            stem=stems.get(number, ""),
            crops=list(mapping[number]),
        )
        path = question_crops_path(crops_dir, number)
        path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def load_question_crops_items(crops_dir: Path) -> dict[int, QuestionCrops] | None:
    """Read ``question_crops/`` files keyed by number; ``None`` when the folder is absent.

    Raises:
        ValueError: malformed file or the same question number in two files.
    """
    source = question_crops_dir(crops_dir)
    if not source.is_dir():
        return None
    items: dict[int, QuestionCrops] = {}
    for path in sorted(source.glob("question_*.json")):
        try:
            item = QuestionCrops.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if item.question_number in items:
            raise ValueError(
                f"{path.name}: question_number {item.question_number} appears twice"
            )
        items[item.question_number] = item
    return items


def load_question_crops(crops_dir: Path) -> QuestionCropMap | None:
    """Read ``question_crops/``; ``None`` when the folder does not exist.

    Raises:
        ValueError: malformed file or the same question number in two files.
    """
    items = load_question_crops_items(crops_dir)
    if items is None:
        return None
    return {number: list(item.crops) for number, item in items.items()}


def validate_question_crops(
    mapping: Mapping[int, list[str]],
    schema_numbers: Iterable[int],
    known_crop_names: Iterable[str],
) -> QuestionCropsReport:
    """Errors: numbers outside kunci, unknown crop names. Warnings: gaps."""
    expected = sorted(set(schema_numbers))
    known = list(dict.fromkeys(known_crop_names))
    known_set = set(known)
    errors: list[str] = []
    for number in sorted(mapping):
        if expected and number not in expected:
            errors.append(f"soal {number} tidak ada di kunci")
        for name in mapping[number]:
            if name not in known_set:
                errors.append(f"soal {number}: crop tidak ditemukan: {name}")
    assigned = {name for names in mapping.values() for name in names}
    return QuestionCropsReport(
        errors=errors,
        missing_questions=[n for n in expected if not mapping.get(n)],
        unassigned_crops=[name for name in known if name not in assigned],
    )
