"""Pure image crop helpers for vision region artifacts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.models.recognition import Region

logger = logging.getLogger(__name__)

_DEFAULT_PAD_RATIO = 0.03
_DEFAULT_MIN_PAD = 8


@dataclass(frozen=True)
class CropResult:
    path: Path
    used_full_page_fallback: bool = False


def clamp_region(region: Region, *, image_width: int, image_height: int) -> Region:
    """Clamp a region to image bounds; empty if fully outside."""
    x = int(max(0, min(int(round(region.x)), image_width)))
    y = int(max(0, min(int(round(region.y)), image_height)))
    width = int(max(0, min(int(round(region.width)), image_width - x)))
    height = int(max(0, min(int(round(region.height)), image_height - y)))
    return Region(x=x, y=y, width=width, height=height)


def normalize_region_to_pixels(
    region: Region,
    *,
    image_width: int,
    image_height: int,
) -> Region:
    """If coordinates look fractional (0..1-ish), scale them to pixels."""
    values = (region.x, region.y, region.width, region.height)
    if all(0 <= float(v) <= 1.5 for v in values) and max(values) <= 1.5:
        return Region(
            x=int(round(float(region.x) * image_width)),
            y=int(round(float(region.y) * image_height)),
            width=int(round(float(region.width) * image_width)),
            height=int(round(float(region.height) * image_height)),
        )
    return Region(
        x=int(region.x),
        y=int(region.y),
        width=int(region.width),
        height=int(region.height),
    )


def expand_region(
    region: Region,
    *,
    image_width: int,
    image_height: int,
    pad_ratio: float = _DEFAULT_PAD_RATIO,
    min_pad: int = _DEFAULT_MIN_PAD,
) -> Region:
    """Expand region by padding, then clamp to image bounds."""
    pad_x = max(min_pad, int(round(image_width * pad_ratio)))
    pad_y = max(min_pad, int(round(image_height * pad_ratio)))
    expanded = Region(
        x=region.x - pad_x,
        y=region.y - pad_y,
        width=region.width + 2 * pad_x,
        height=region.height + 2 * pad_y,
    )
    return clamp_region(
        expanded, image_width=image_width, image_height=image_height
    )


def union_regions(regions: list[Region]) -> Region | None:
    """Axis-aligned union of regions; None if empty."""
    if not regions:
        return None
    x0 = min(r.x for r in regions)
    y0 = min(r.y for r in regions)
    x1 = max(r.x + r.width for r in regions)
    y1 = max(r.y + r.height for r in regions)
    return Region(x=x0, y=y0, width=x1 - x0, height=y1 - y0)


def prepare_crop_region(
    region: Region,
    *,
    image_width: int,
    image_height: int,
    pad_ratio: float = _DEFAULT_PAD_RATIO,
    min_pad: int = _DEFAULT_MIN_PAD,
) -> Region:
    """Normalize → expand → clamp for a safe crop box."""
    normalized = normalize_region_to_pixels(
        region, image_width=image_width, image_height=image_height
    )
    return expand_region(
        normalized,
        image_width=image_width,
        image_height=image_height,
        pad_ratio=pad_ratio,
        min_pad=min_pad,
    )


def crop_region(
    image_path: Path,
    region: Region,
    output_path: Path,
    *,
    pad_ratio: float = _DEFAULT_PAD_RATIO,
    min_pad: int = _DEFAULT_MIN_PAD,
) -> CropResult:
    """Crop ``region`` from ``image_path`` and save to ``output_path`` (PNG).

    Normalizes fractional coords, expands with padding, then clamps.
    If the prepared box is empty/invalid, falls back to a full-page copy and
    sets ``used_full_page_fallback`` (logged as a warning).
    """
    from PIL import Image

    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:
        width, height = image.size
        prepared = prepare_crop_region(
            region,
            image_width=width,
            image_height=height,
            pad_ratio=pad_ratio,
            min_pad=min_pad,
        )
        used_fallback = prepared.width <= 0 or prepared.height <= 0
        if used_fallback:
            logger.warning(
                "empty crop box for %s region=%s; saving full-page fallback",
                image_path.name,
                region.model_dump(),
            )
            cropped = image.copy()
        else:
            box = (
                prepared.x,
                prepared.y,
                prepared.x + prepared.width,
                prepared.y + prepared.height,
            )
            cropped = image.crop(box)
        cropped.save(output_path, format="PNG")
    return CropResult(path=output_path, used_full_page_fallback=used_fallback)
