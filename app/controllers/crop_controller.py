"""Propose ink crops, recrop from editable JSON, interactive confirm loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.functions.page_names import page_image_filename
from app.functions.regions_artifact import crop_filename, regions_json_path
from app.interfaces.renderer import PdfRenderer
from app.models.page import Page
from app.services.vision.recognizer import OllamaVisionRecognizer
from app.views.crop_view import (
    ask_crops_ok,
    print_crop_summary,
    should_prompt_interactively,
    wait_for_json_edit,
)


@dataclass(frozen=True)
class PageCropSummary:
    page_number: int
    json_path: Path
    crop_paths: list[Path]
    source: str


@dataclass(frozen=True)
class CropProposeResult:
    pages: list[PageCropSummary]
    crops_dir: Path


class CropController:
    def __init__(
        self,
        *,
        renderer: PdfRenderer,
        recognizer: OllamaVisionRecognizer,
    ) -> None:
        self._renderer = renderer
        self._recognizer = recognizer

    @property
    def crops_dir(self) -> Path:
        return self._recognizer.crops_dir

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
            image_path = Path(pages_dir) / page.image
            regions, source, json_path = self._recognizer.propose_page_crops(
                image_path, page.page_number
            )
            page_dir = self._recognizer.page_crop_dir(page.page_number)
            crop_paths = [page_dir / crop_filename(i) for i in range(len(regions))]
            summary = PageCropSummary(
                page_number=page.page_number,
                json_path=json_path,
                crop_paths=crop_paths,
                source=source,
            )
            print_crop_summary(
                page_number=summary.page_number,
                json_path=summary.json_path,
                crop_paths=summary.crop_paths,
            )
            summaries.append(summary)
        return CropProposeResult(pages=summaries, crops_dir=self.crops_dir)

    def recrop_all(self, pages_dir: Path) -> CropProposeResult:
        """Recrop every page that has ``page_*_regions.json`` under crops_dir."""
        pages_dir = Path(pages_dir)
        summaries: list[PageCropSummary] = []
        crops_root = self.crops_dir
        if not crops_root.is_dir():
            return CropProposeResult(pages=[], crops_dir=crops_root)

        for page_dir in sorted(crops_root.glob("page_*")):
            if not page_dir.is_dir():
                continue
            try:
                page_number = int(page_dir.name.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            json_path = regions_json_path(page_dir, page_number)
            if not json_path.is_file():
                continue
            image_path = pages_dir / page_image_filename(page_number)
            if not image_path.is_file():
                raise FileNotFoundError(
                    f"page image missing for recrop: {image_path}"
                )
            regions, source, json_path = self._recognizer.recrop_page_from_json(
                image_path, page_number
            )
            crop_paths = [page_dir / crop_filename(i) for i in range(len(regions))]
            summary = PageCropSummary(
                page_number=page_number,
                json_path=json_path,
                crop_paths=crop_paths,
                source=source,
            )
            print_crop_summary(
                page_number=summary.page_number,
                json_path=summary.json_path,
                crop_paths=summary.crop_paths,
            )
            summaries.append(summary)
        return CropProposeResult(pages=summaries, crops_dir=crops_root)

    def confirm_loop(
        self,
        pages_dir: Path,
        *,
        force_yes: bool = False,
        input_fn=input,
    ) -> None:
        """Ask until crops OK; on no, wait for JSON edit then recrop."""
        if force_yes:
            return
        # Custom input_fn (tests) always prompts; real stdin needs a TTY.
        if input_fn is input and not should_prompt_interactively(force_yes=False):
            return
        pages_dir = Path(pages_dir)
        while True:
            if ask_crops_ok(input_fn=input_fn):
                return
            hint = str(self.crops_dir / "page_*/page_*_regions.json")
            wait_for_json_edit(json_hint=hint, input_fn=input_fn)
            result = self.recrop_all(pages_dir)
            if not result.pages:
                print("No regions JSON found under crops/; cannot recrop.")

    def ensure_crops_confirmed(
        self,
        pages: list[Page],
        pages_dir: Path,
        *,
        use_existing: bool = False,
        force_yes: bool = False,
        input_fn=input,
    ) -> CropProposeResult:
        """Propose (unless existing) then run confirm loop before VLM."""
        pages_dir = Path(pages_dir)
        if use_existing and all(
            regions_json_path(
                self._recognizer.page_crop_dir(p.page_number), p.page_number
            ).is_file()
            for p in pages
        ):
            summaries: list[PageCropSummary] = []
            for page in pages:
                page_dir = self._recognizer.page_crop_dir(page.page_number)
                json_path = regions_json_path(page_dir, page.page_number)
                from app.functions.regions_artifact import load_regions_artifact

                _n, source, regions = load_regions_artifact(json_path)
                crop_paths = [
                    page_dir / crop_filename(i) for i in range(len(regions))
                ]
                summary = PageCropSummary(
                    page_number=page.page_number,
                    json_path=json_path,
                    crop_paths=crop_paths,
                    source=source,
                )
                print_crop_summary(
                    page_number=summary.page_number,
                    json_path=summary.json_path,
                    crop_paths=summary.crop_paths,
                )
                summaries.append(summary)
            result = CropProposeResult(pages=summaries, crops_dir=self.crops_dir)
        else:
            result = self.propose_pages(pages, pages_dir)
        self.confirm_loop(pages_dir, force_yes=force_yes, input_fn=input_fn)
        return result
