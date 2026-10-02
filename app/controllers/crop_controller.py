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
    ) -> CropProposeResult | None:
        """Ask until crops OK; on no, wait for JSON edit then recrop.

        After a failed recrop the crops on disk are stale, so the loop asks for
        another edit instead of offering "OK?" (whose default is yes).

        Returns the last successful recrop, or ``None`` if nothing was recropped.
        """
        if force_yes or not is_interactive(input_fn):
            return None
        pages_dir = Path(pages_dir)
        pending: Exception | None = None
        latest: CropProposeResult | None = None
        while True:
            if pending is None and ask_crops_ok(input_fn=input_fn):
                return latest
            edited = wait_for_json_edit(
                json_hint=str(self.crops_dir / REGIONS_JSON_HINT), input_fn=input_fn
            )
            if not edited and pending is not None:
                raise pending
            try:
                result = self.recrop_all(pages_dir)
            except (MathGraderError, ValueError) as exc:
                # A bad JSON edit should re-prompt, not abort the whole session.
                print_error(exc)
                pending = exc
                continue
            if not result.pages:
                pending = NoRegionsJsonError(self.crops_dir)
                print_error(pending)
                continue
            pending = None
            latest = result

    def ensure_crops_confirmed(
        self,
        pages: list[Page],
        pages_dir: Path,
        *,
        use_existing: bool = False,
        force_yes: bool = False,
        input_fn: InputFn | None = None,
    ) -> CropProposeResult:
        """Propose (unless existing) then run confirm loop before VLM.

        With ``use_existing`` only pages lacking a regions JSON are proposed, so
        hand-edited boxes on the other pages survive.
        """
        pages_dir = Path(pages_dir)
        if use_existing:
            existing = [p for p in pages if self._has_regions(p.page_number)]
            missing = [p for p in pages if not self._has_regions(p.page_number)]
            summaries = [self._summarize_existing(p.page_number) for p in existing]
            if missing:
                summaries += self.propose_pages(missing, pages_dir).pages
            result = CropProposeResult(
                pages=sorted(summaries, key=lambda s: s.page_number)
            )
        else:
            result = self.propose_pages(pages, pages_dir)
        recropped = self.confirm_loop(pages_dir, force_yes=force_yes, input_fn=input_fn)
        return recropped or result

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
