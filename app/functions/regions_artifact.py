"""Pure helpers for page region crop artifacts (editable bbox JSON)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.models.recognition import DetectedRegion, Region

_CROP_NAME_RE = re.compile(r"^page_(\d+)_region_\d+")
_PAGE_DIR_RE = re.compile(r"^page_(\d+)$")
CROP_SUFFIX = "_solution.png"


def regions_json_path(page_crop_dir: Path, page_number: int) -> Path:
    """Canonical path: ``page_NNN_regions.json`` under the page crop dir."""
    if page_number < 1:
        raise ValueError(f"page_number must be >= 1, got {page_number}")
    return Path(page_crop_dir) / f"page_{page_number:03d}_regions.json"


def crop_filename(page_number: int, index: int) -> str:
    if page_number < 1:
        raise ValueError(f"page_number must be >= 1, got {page_number}")
    return f"page_{page_number:03d}_region_{index:02d}{CROP_SUFFIX}"


def crop_display_name(name: str) -> str:
    """Short crop label for terminal output (``page_001_region_00``)."""
    return Path(name).name.removesuffix(CROP_SUFFIX)


def crop_paths_for(page_crop_dir: Path, page_number: int, count: int) -> list[Path]:
    return [Path(page_crop_dir) / crop_filename(page_number, i) for i in range(count)]


def list_page_crop_dirs(crops_dir: Path) -> list[tuple[int, Path]]:
    """``(page_number, dir)`` for every ``page_NNN`` folder under ``crops_dir``."""
    crops_dir = Path(crops_dir)
    if not crops_dir.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    for child in sorted(crops_dir.iterdir()):
        match = _PAGE_DIR_RE.match(child.name)
        if child.is_dir() and match is not None and int(match.group(1)) >= 1:
            found.append((int(match.group(1)), child))
    return found


def crop_page_number(name: str) -> int | None:
    """Page number encoded in a crop file name (``page_NNN_region_...``)."""
    match = _CROP_NAME_RE.match(Path(name).name)
    if match is None:
        return None
    page = int(match.group(1))
    return page if page >= 1 else None


def normalize_region_orders(regions: list[DetectedRegion]) -> list[DetectedRegion]:
    """Make ``order`` a permutation of ``0..n-1``.

    Distinct orders are a deliberate reading order and keep their ranking.
    A repeated order means a hand-copied entry, so the list position (which
    also names the crop file) wins.
    """
    orders = [r.order for r in regions]
    if len(set(orders)) == len(orders):
        ranked = sorted(range(len(regions)), key=lambda i: orders[i])
        new_orders = {index: rank for rank, index in enumerate(ranked)}
    else:
        new_orders = {index: index for index in range(len(regions))}
    return [
        r if r.order == new_orders[i] else r.model_copy(update={"order": new_orders[i]})
        for i, r in enumerate(regions)
    ]


def region_dicts_with_crop_paths(
    regions: list[DetectedRegion], page_number: int
) -> list[dict[str, Any]]:
    """Serialize regions with relative ``crop_path`` for the page crop dir."""
    return [
        {
            **r.model_dump(),
            "crop_path": crop_filename(page_number, i),
        }
        for i, r in enumerate(normalize_region_orders(regions))
    ]


def write_regions_artifact(
    page_crop_dir: Path,
    page_number: int,
    *,
    regions: list[DetectedRegion],
    source: str,
) -> Path:
    """Write flat ``page_NNN_regions.json`` (single editable source of truth)."""
    page_crop_dir = Path(page_crop_dir)
    page_crop_dir.mkdir(parents=True, exist_ok=True)
    path = regions_json_path(page_crop_dir, page_number)
    payload = {
        "page_number": page_number,
        "source": source,
        "regions": region_dicts_with_crop_paths(regions, page_number),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_regions_artifact(path: Path) -> tuple[int, str, list[DetectedRegion]]:
    """Load regions from canonical JSON; ignore unknown fields like crop_path."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    page_number = int(raw.get("page_number") or 0)
    source = str(raw.get("source") or "ink")
    items = raw.get("regions")
    if not isinstance(items, list):
        # Backward compat: hybrid ``selected`` / ``ink`` shapes
        items = raw.get("ink") if isinstance(raw.get("ink"), list) else []
        if not items and isinstance(raw.get("selected"), list):
            items = [
                s.get("detected")
                for s in raw["selected"]
                if isinstance(s, dict) and isinstance(s.get("detected"), dict)
            ]
    regions: list[DetectedRegion] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        region_raw = item.get("region")
        if not isinstance(region_raw, dict):
            continue
        region = Region(
            x=float(region_raw.get("x") or 0),
            y=float(region_raw.get("y") or 0),
            width=float(region_raw.get("width") or 0),
            height=float(region_raw.get("height") or 0),
        )
        order_raw = item.get("order")
        regions.append(
            DetectedRegion(
                type=item.get("type") or "solution",  # type: ignore[arg-type]
                region=region,
                question_number=int(item.get("question_number") or 0),
                order=int(order_raw) if order_raw is not None else index,
            )
        )
    return page_number, source, normalize_region_orders(regions)


def page_has_regions_artifact(page_crop_dir: Path, page_number: int) -> bool:
    return regions_json_path(page_crop_dir, page_number).is_file()


# Below ~1.5 px every coordinate would read as a page fraction (image_crop).
MIN_REGION_SIDE_PX = 4
_BOUNDS_TOLERANCE_PX = 1.0


def manual_region_errors(
    regions: list[DetectedRegion], *, image_width: int, image_height: int
) -> list[str]:
    """Problems with hand-drawn pixel boxes; empty when every box is usable."""
    if not regions:
        return ["minimal satu kotak per halaman"]
    errors: list[str] = []
    for number, detected in enumerate(regions, start=1):
        box = detected.region
        if box.width < MIN_REGION_SIDE_PX or box.height < MIN_REGION_SIDE_PX:
            errors.append(f"kotak {number}: lebar dan tinggi minimal {MIN_REGION_SIDE_PX} px")
            continue
        if (
            box.x < -_BOUNDS_TOLERANCE_PX
            or box.y < -_BOUNDS_TOLERANCE_PX
            or box.x + box.width > image_width + _BOUNDS_TOLERANCE_PX
            or box.y + box.height > image_height + _BOUNDS_TOLERANCE_PX
        ):
            errors.append(
                f"kotak {number}: di luar halaman ({image_width}x{image_height} px)"
            )
    return errors
