"""Propose ink crops and save boxes edited in the crop editor."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import InvalidRegionsError, PageImageMissingError
from app.functions.image_crop import MANUAL_REGION_SOURCE
from app.functions.page_names import page_image_filename
from app.functions.pages_artifact import load_pages_from_dir
from app.functions.regions_artifact import (
    crop_paths_for,
    load_regions_artifact,
    manual_region_errors,
    page_has_regions_artifact,
    regions_json_path,
)
from app.interfaces.crop_workspace import CropWorkspace
from app.interfaces.renderer import PdfRenderer
from app.models.crop import CropProposeResult, PageCropSummary, PageRegions
from app.models.page import Page
from app.models.recognition import DetectedRegion

logger = logging.getLogger(__name__)


class CropController:
    def __init__(
        self,
        *,
        renderer: PdfRenderer,
        workspace: CropWorkspace,
    ) -> None:
        self._renderer = renderer
        self._workspace = workspace

    @property
    def crops_dir(self) -> Path:
        return self._workspace.crops_dir

    def propose_for_pdf(
        self,
        pdf_path: Path,
        pages_dir: Path,
        dpi: int,
    ) -> CropProposeResult:
        pages = self._renderer.render(pdf_path, pages_dir, dpi)
        return self.propose_pages(pages, pages_dir)

    def propose_pages(
        self, pages: list[Page], pages_dir: Path
    ) -> CropProposeResult:
        summaries: list[PageCropSummary] = []
        for page in pages:
            regions, _, json_path = self._workspace.propose_page_crops(
                Path(pages_dir) / page.image, page.page_number
            )
            summaries.append(
                self._summarize_page(page.page_number, json_path, len(regions))
            )
        return CropProposeResult(pages=summaries)

    def ensure_crops(
        self,
        pages: list[Page],
        pages_dir: Path,
        *,
        use_existing: bool = False,
    ) -> CropProposeResult:
        """Crops for every page before the VLM runs.

        With ``use_existing`` only pages lacking a regions JSON are proposed, so
        boxes edited in the crop editor survive.
        """
        pages_dir = Path(pages_dir)
        if not use_existing:
            return self.propose_pages(pages, pages_dir)
        existing = [p for p in pages if self._has_regions(p.page_number)]
        missing = [p for p in pages if not self._has_regions(p.page_number)]
        summaries = [self._summarize_existing(p.page_number) for p in existing]
        if missing:
            summaries += self.propose_pages(missing, pages_dir).pages
        return CropProposeResult(pages=sorted(summaries, key=lambda s: s.page_number))

    def load_page_regions(self, page_number: int, pages_dir: Path) -> PageRegions:
        """Page size + current boxes for the crop editor (empty when not proposed yet)."""
        page = self._page(page_number, pages_dir)
        json_path = regions_json_path(self._workspace.page_crop_dir(page_number), page_number)
        source, regions = "", []
        if json_path.is_file():
            _n, source, regions = load_regions_artifact(json_path)
        return PageRegions(
            page_number=page.page_number,
            image=page.image,
            width=page.width,
            height=page.height,
            source=source,
            regions=regions,
        )

    def save_page_regions(
        self, page_number: int, regions: list[DetectedRegion], pages_dir: Path
    ) -> PageCropSummary:
        """Replace one page's boxes with hand-drawn ones and recrop it (no padding)."""
        page = self._page(page_number, pages_dir)
        errors = manual_region_errors(
            regions, image_width=page.width, image_height=page.height
        )
        if errors:
            raise InvalidRegionsError(errors)
        image_path = Path(pages_dir) / page.image
        if not image_path.is_file():
            raise PageImageMissingError(image_path)
        saved, _source, json_path = self._workspace.save_page_regions(
            image_path, page_number, regions, source=MANUAL_REGION_SOURCE
        )
        page_dir = self._workspace.page_crop_dir(page_number)
        return PageCropSummary(
            page_number=page_number,
            json_path=json_path,
            crop_paths=crop_paths_for(page_dir, page_number, len(saved)),
        )

    @staticmethod
    def _page(page_number: int, pages_dir: Path) -> Page:
        try:
            pages = load_pages_from_dir(pages_dir)
        except (FileNotFoundError, ValueError) as exc:
            raise PageImageMissingError(Path(pages_dir) / page_image_filename(page_number)) from exc
        for page in pages:
            if page.page_number == page_number:
                return page
        raise PageImageMissingError(Path(pages_dir) / page_image_filename(page_number))

    def _has_regions(self, page_number: int) -> bool:
        return page_has_regions_artifact(
            self._workspace.page_crop_dir(page_number), page_number
        )

    def _summarize_existing(self, page_number: int) -> PageCropSummary:
        page_dir = self._workspace.page_crop_dir(page_number)
        json_path = regions_json_path(page_dir, page_number)
        _n, _source, regions = load_regions_artifact(json_path)
        return self._summarize_page(page_number, json_path, len(regions))

    def _summarize_page(
        self, page_number: int, json_path: Path, region_count: int
    ) -> PageCropSummary:
        page_dir = self._workspace.page_crop_dir(page_number)
        logger.info("page %d: %d crop(s) in %s", page_number, region_count, json_path)
        return PageCropSummary(
            page_number=page_number,
            json_path=json_path,
            crop_paths=crop_paths_for(page_dir, page_number, region_count),
        )
