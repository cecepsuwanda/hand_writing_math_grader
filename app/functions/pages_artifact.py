"""Load rendered page metadata from disk."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from app.functions.page_names import PAGES_METADATA_FILENAME, page_image_filename
from app.functions.regions_artifact import page_has_regions_artifact
from app.models.page import Page


def load_pages_from_dir(pages_dir: Path) -> list[Page]:
    """Load ``pages.json`` or discover ``page_NNN.png`` files."""
    pages_dir = Path(pages_dir)
    meta = pages_dir / PAGES_METADATA_FILENAME
    if meta.is_file():
        raw = json.loads(meta.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"empty or invalid pages metadata: {meta}")
        return [Page.model_validate(item) for item in raw]

    pages: list[Page] = []
    for path in sorted(pages_dir.glob("page_*.png")):
        try:
            number = int(path.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if page_image_filename(number) != path.name:
            continue
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
        pages.append(
            Page(
                page_number=number,
                image=path.name,
                width=width,
                height=height,
            )
        )
    if not pages:
        raise FileNotFoundError(f"no pages found under {pages_dir}")
    return pages


def crops_regions_present(crops_dir: Path) -> bool:
    """True if at least one ``page_*/page_*_regions.json`` exists."""
    crops_dir = Path(crops_dir)
    if not crops_dir.is_dir():
        return False
    return any(crops_dir.glob("page_*/page_*_regions.json"))


def pages_missing_regions(crops_dir: Path, page_numbers: Iterable[int]) -> list[int]:
    """Page numbers without ``page_NNN/page_NNN_regions.json`` under ``crops_dir``."""
    crops_dir = Path(crops_dir)
    return [
        number
        for number in page_numbers
        if not page_has_regions_artifact(crops_dir / f"page_{number:03d}", number)
    ]
