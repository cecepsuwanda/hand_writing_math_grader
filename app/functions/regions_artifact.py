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
REGIONS_JSON_HINT = "page_*/page_*_regions.json"


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


def region_dicts_with_crop_paths(
    regions: list[DetectedRegion], page_number: int
) -> list[dict[str, Any]]:
    """Serialize regions with relative ``crop_path`` for the page crop dir."""
    return [
        {
            **r.model_dump(),
            "crop_path": crop_filename(page_number, i),
        }
        for i, r in enumerate(regions)
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
    return page_number, source, regions


def page_has_regions_artifact(page_crop_dir: Path, page_number: int) -> bool:
    return regions_json_path(page_crop_dir, page_number).is_file()
