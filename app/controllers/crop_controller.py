"""Propose ink crops, recrop from editable JSON, interactive confirm loop."""

from __future__ import annotations

from pathlib import Path

from app.exceptions import MathGraderError, NoRegionsJsonError, PageImageMissingError
from app.functions.page_names import page_image_filename
from app.functions.regions_artifact import (
    REGIONS_JSON_HINT,
    crop_paths_for,
    list_page_crop_dirs,
    load_regions_artifact,
    page_has_regions_artifact,
    regions_json_path,
)
from app.interfaces.crop_workspace import CropWorkspace
from app.interfaces.renderer import PdfRenderer
from app.models.crop import CropProposeResult, PageCropSummary
from app.models.page import Page
from app.views.crop_view import ask_crops_ok, print_crop_summary, wait_for_json_edit
from app.views.error_view import print_error
from app.views.prompt_view import InputFn, is_interactive


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

    def recrop_all(self, pages_dir: Path) -> CropProposeResult:
        """Recrop every page that has ``page_*_regions.json`` under crops_dir."""
        pages_dir = Path(pages_dir)
        summaries: list[PageCropSummary] = []
        for page_number, page_dir in list_page_crop_dirs(self.crops_dir):
            if not page_has_regions_artifact(page_dir, page_number):
                continue
            image_path = pages_dir / page_image_filename(page_number)
            if not image_path.is_file():
                raise PageImageMissingError(image_path)
            regions, _, json_path = self._workspace.recrop_page_from_json(
                image_path, page_number
            )
            summaries.append(
                self._summarize_page(page_number, json_path, len(regions), page_dir)
            )
        return CropProposeResult(pages=summaries)

    def confirm_loop(
        self,
        pages_dir: Path,
        *,
        force_yes: bool = False,
        input_fn: InputFn | None = None,
    ) -> None:
        """Ask until crops OK; on no, wait for JSON edit then recrop."""
        if force_yes or not is_interactive(input_fn):
            return
        pages_dir = Path(pages_dir)
        while True:
            if ask_crops_ok(input_fn=input_fn):
                return
            wait_for_json_edit(
                json_hint=str(self.crops_dir / REGIONS_JSON_HINT), input_fn=input_fn
            )
            try:
                result = self.recrop_all(pages_dir)
            except (MathGraderError, ValueError) as exc:
                # A bad JSON edit should re-prompt, not abort the whole session.
                print_error(exc)
                continue
            if not result.pages:
                print_error(NoRegionsJsonError(self.crops_dir))

    def ensure_crops_confirmed(
        self,
        pages: list[Page],
        pages_dir: Path,
        *,
        use_existing: bool = False,
        force_yes: bool = False,
        input_fn: InputFn | None = None,
    ) -> CropProposeResult:
        """Propose (unless existing) then run confirm loop before VLM."""
        pages_dir = Path(pages_dir)
        if use_existing and all(
            page_has_regions_artifact(
                self._workspace.page_crop_dir(p.page_number), p.page_number
            )
            for p in pages
        ):
            result = CropProposeResult(
                pages=[self._summarize_existing(p.page_number) for p in pages]
            )
        else:
            result = self.propose_pages(pages, pages_dir)
        self.confirm_loop(pages_dir, force_yes=force_yes, input_fn=input_fn)
        return result

    def _summarize_existing(self, page_number: int) -> PageCropSummary:
        page_dir = self._workspace.page_crop_dir(page_number)
        json_path = regions_json_path(page_dir, page_number)
        _n, _source, regions = load_regions_artifact(json_path)
        return self._summarize_page(page_number, json_path, len(regions))

    def _summarize_page(
        self,
        page_number: int,
        json_path: Path,
        region_count: int,
        page_dir: Path | None = None,
    ) -> PageCropSummary:
        page_dir = page_dir or self._workspace.page_crop_dir(page_number)
        summary = PageCropSummary(
            page_number=page_number,
            json_path=json_path,
            crop_paths=crop_paths_for(page_dir, page_number, region_count),
        )
        print_crop_summary(summary)
        return summary
