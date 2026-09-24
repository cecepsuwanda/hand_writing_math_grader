"""Tests for regions artifact + crop confirm / recrop (no live Ollama)."""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image
from app.controllers.crop_controller import CropController
from app.functions.regions_artifact import (
    load_regions_artifact,
    regions_json_path,
    write_regions_artifact,
)
from app.interfaces.crop_workspace import CropWorkspace
from app.models.page import Page
from app.models.recognition import DetectedRegion, Region
from app.services.vision.ink_region_proposer import InkRegionProposer
from app.services.vision.recognizer import OllamaVisionRecognizer
from app.views.crop_view import print_no_regions_json


class TestRegionsArtifact:

    def test_write_load_regions_artifact_flat(self, tmp_path: Path) -> None:
        page_dir = tmp_path / "page_001"
        regions = [
            DetectedRegion(
                type="solution",
                region=Region(x=1, y=2, width=3, height=4),
                question_number=0,
                order=0,
            )
        ]
        path = write_regions_artifact(page_dir, 1, regions=regions, source="ink")
        assert path.name == "page_001_regions.json"
        assert not (page_dir / "page_001_regions_ink.json").exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "selected" not in payload
        assert "ink" not in payload
        assert payload["regions"][0]["crop_path"] == "region_00_solution.png"
        _n, source, loaded = load_regions_artifact(path)
        assert source == "ink"
        assert loaded[0].region.width == 3

    def test_propose_does_not_write_regions_ink(self, tmp_path: Path) -> None:
        image = tmp_path / "page.png"
        Image.new("RGB", (40, 40), color=(255, 255, 255)).save(image)

        class _One(InkRegionProposer):
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=0, y=0, width=20, height=20),
                        order=0,
                    )
                ]

        recognizer = OllamaVisionRecognizer(
            client=object(),  # type: ignore[arg-type]
            model="m",
            output_dir=tmp_path / "rec",
            crops_dir=tmp_path / "crops",
            proposer=_One(),
        )
        regions, source, json_path = recognizer.propose_page_crops(image, 1)
        assert source == "ink"
        assert len(regions) == 1
        assert json_path.is_file()
        assert (tmp_path / "crops" / "page_001" / "region_00_solution.png").is_file()
        assert not (tmp_path / "crops" / "page_001" / "page_001_regions_ink.json").exists()

    def test_recrop_from_edited_json(self, tmp_path: Path) -> None:
        image = tmp_path / "page.png"
        Image.new("RGB", (100, 100), color=(255, 255, 255)).save(image)
        crops = tmp_path / "crops"
        recognizer = OllamaVisionRecognizer(
            client=object(),  # type: ignore[arg-type]
            model="m",
            output_dir=tmp_path / "rec",
            crops_dir=crops,
            proposer=InkRegionProposer(),
        )
        page_dir = crops / "page_001"
        write_regions_artifact(
            page_dir,
            1,
            regions=[
                DetectedRegion(
                    type="solution",
                    region=Region(x=0, y=0, width=10, height=10),
                    order=0,
                )
            ],
            source="ink",
        )
        recognizer.recrop_page_from_json(image, 1)
        crop_a = page_dir / "region_00_solution.png"
        assert crop_a.is_file()
        size_a = crop_a.stat().st_size

        # Edit JSON box larger
        payload = json.loads(regions_json_path(page_dir, 1).read_text(encoding="utf-8"))
        payload["regions"][0]["region"] = {"x": 0, "y": 0, "width": 80, "height": 80}
        regions_json_path(page_dir, 1).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        recognizer.recrop_page_from_json(image, 1)
        size_b = crop_a.stat().st_size
        assert size_b > size_a


class TestCropConfirm:

    def test_confirm_loop_n_then_y(self, tmp_path: Path) -> None:
        image = tmp_path / "pages" / "page_001.png"
        image.parent.mkdir(parents=True)
        Image.new("RGB", (30, 30), color=(255, 255, 255)).save(image)
        crops = tmp_path / "crops"
        page_dir = crops / "page_001"
        write_regions_artifact(
            page_dir,
            1,
            regions=[
                DetectedRegion(
                    type="solution",
                    region=Region(x=0, y=0, width=10, height=10),
                    order=0,
                )
            ],
            source="ink",
        )

        class _FakeRenderer:
            def render(self, pdf_path, pages_dir, dpi):
                raise AssertionError("render should not run")

        recognizer = OllamaVisionRecognizer(
            client=object(),  # type: ignore[arg-type]
            model="m",
            output_dir=tmp_path / "rec",
            crops_dir=crops,
        )
        controller = CropController(renderer=_FakeRenderer(), recognizer=recognizer)
        answers = iter(["n", "", "y"])
        controller.confirm_loop(
            tmp_path / "pages",
            force_yes=False,
            input_fn=lambda _prompt="": next(answers),
        )

    def test_crop_controller_accepts_crop_workspace_port(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        image = pages_dir / "page_001.png"
        Image.new("RGB", (20, 20), color=(255, 255, 255)).save(image)
        crops = tmp_path / "crops"

        class _FakeCrop(CropWorkspace):
            def __init__(self) -> None:
                self._crops = crops

            @property
            def crops_dir(self) -> Path:
                return self._crops

            def page_crop_dir(self, page_number: int) -> Path:
                return self._crops / f"page_{page_number:03d}"

            def propose_page_crops(self, image_path: Path, page_number: int):
                page_dir = self.page_crop_dir(page_number)
                regions = [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=0, y=0, width=10, height=10),
                        order=0,
                    )
                ]
                path = write_regions_artifact(
                    page_dir, page_number, regions=regions, source="ink"
                )
                return regions, "ink", path

            def recrop_page_from_json(self, image_path: Path, page_number: int):
                return self.propose_page_crops(image_path, page_number)

        class _FakeRenderer:
            def render(self, pdf_path, pages_dir, dpi):
                raise AssertionError("unused")

        controller = CropController(renderer=_FakeRenderer(), recognizer=_FakeCrop())
        pages = [Page(page_number=1, width=20, height=20, image="page_001.png")]
        result = controller.ensure_crops_confirmed(pages, pages_dir, force_yes=True)
        assert len(result.pages) == 1
        assert result.pages[0].json_path.is_file()

    def test_print_no_regions_json(self, capsys) -> None:
        crops = Path("data") / "output" / "crops"
        print_no_regions_json(crops)
        captured = capsys.readouterr()
        assert str(crops) in captured.out

    def test_ensure_propose_with_force_yes(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        image = pages_dir / "page_001.png"
        Image.new("RGB", (40, 40), color=(240, 240, 240)).save(image)

        class _One(InkRegionProposer):
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=0, y=0, width=15, height=15),
                        order=0,
                    )
                ]

        recognizer = OllamaVisionRecognizer(
            client=object(),  # type: ignore[arg-type]
            model="m",
            output_dir=tmp_path / "rec",
            crops_dir=tmp_path / "crops",
            proposer=_One(),
        )

        class _FakeRenderer:
            def render(self, pdf_path, pages_dir, dpi):
                raise AssertionError("unused")

        controller = CropController(renderer=_FakeRenderer(), recognizer=recognizer)
        pages = [Page(page_number=1, width=40, height=40, image="page_001.png")]
        result = controller.ensure_crops_confirmed(
            pages, pages_dir, force_yes=True
        )
        assert len(result.pages) == 1
        assert result.pages[0].json_path.is_file()
