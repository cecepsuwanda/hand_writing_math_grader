"""Tests for regions artifact, crop editor, labels and review (no live Ollama)."""
from __future__ import annotations
import json
import logging
from pathlib import Path

import pytest
from PIL import Image

from app.config import AppConfig, GradingConfig
from app.controllers.crop_controller import CropController
from app.controllers.question_label_controller import QuestionLabelController
from app.exceptions import (
    EmptyRegionsError,
    ExamSchemaMissingError,
    InvalidRegionsError,
    MathGraderError,
    NoRegionsForLabelingError,
    QuestionCropsInvalidError,
    RegionsArtifactMissingError,
)
from app.functions.image_crop import MANUAL_REGION_SOURCE, CropPadding, crop_padding_for
from app.functions.question_crops import (
    assign_by_labels,
    assign_sequential,
    crop_to_questions,
    list_crops_in_reading_order,
    load_question_crops,
    mapping_from_crop_labels,
    question_crops_dir,
    question_crops_path,
    validate_question_crops,
    write_question_crops,
)
from app.functions.regions_artifact import (
    crop_display_name,
    crop_filename,
    crop_paths_for,
    list_page_crop_dirs,
    load_regions_artifact,
    manual_region_errors,
    regions_json_path,
    write_regions_artifact,
)
from app.interfaces.crop_workspace import CropWorkspace
from app.models.exam_schema import ExamQuestion, ExamSchema
from app.models.page import Page
from app.models.question_crops import LabelSource
from app.models.recognition import DetectedRegion, Region
from app.services.math.preview import symbolic_preview_latex
from app.services.pipeline_factory import build_question_label_controller
from app.services.vision.question_labeler import OllamaQuestionLabeler
from app.web.jobs import JobStatus
from app.web.schemas import parse_crop_labels
from tests.support.asserts import assert_contains
from tests.support.builders import (
    make_question,
    make_step,
    single_question_json,
    write_png,
    write_question_dir,
    write_run_pages,
)
from tests.support.fakes import FakeClient, FakeProposer
from tests.support.harness import WebHarness, make_recognizer, q1_standard


def _schema(count: int) -> ExamSchema:
    return ExamSchema(
        questions=[ExamQuestion(number=n, stem=f"soal {n}") for n in range(1, count + 1)]
    )


def _write_regions(crops_dir: Path, page_number: int, count: int) -> list[str]:
    """``count`` stacked regions on one page; returns crop file names in order."""
    write_regions_artifact(
        crops_dir / f"page_{page_number:03d}",
        page_number,
        regions=[
            DetectedRegion(
                type="solution",
                region=Region(x=0, y=10 * i, width=20, height=10),
                order=i,
            )
            for i in range(count)
        ],
        source="ink",
    )
    return [crop_filename(page_number, i) for i in range(count)]


class _FakeLabeler:
    def __init__(self, labels: dict[str, list[int] | None]) -> None:
        self._labels = labels
        self.seen: list[Path] = []

    def detect(self, crop_path: Path) -> list[int] | None:
        self.seen.append(crop_path)
        return self._labels.get(Path(crop_path).name, [])


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
        assert payload["regions"][0]["crop_path"] == "page_001_region_00_solution.png"
        _n, source, loaded = load_regions_artifact(path)
        assert source == "ink"
        assert loaded[0].region.width == 3

    @pytest.mark.parametrize(
        ("orders", "written"),
        [
            ([0, 1, 1], [0, 1, 2]),
            ([5, 5, 5], [0, 1, 2]),
            ([2, 0, 1], [2, 0, 1]),
            ([10, 30, 20], [0, 2, 1]),
        ],
    )
    def test_saved_orders_are_a_permutation(
        self, tmp_path: Path, orders: list[int], written: list[int]
    ) -> None:
        regions = [
            DetectedRegion(type="solution", region=Region(x=0, y=10 * i, width=5, height=5), order=order)
            for i, order in enumerate(orders)
        ]
        path = write_regions_artifact(tmp_path / "page_001", 1, regions=regions, source="manual")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert [item["order"] for item in payload["regions"]] == written
        assert [r.order for r in load_regions_artifact(path)[2]] == written

    def test_list_page_crop_dirs_skips_non_page_entries(self, tmp_path: Path) -> None:
        for name in ("page_002", "page_001", "page_000", "page_x", "question_crops"):
            (tmp_path / name).mkdir()
        (tmp_path / "page_003").write_text("not a dir", encoding="utf-8")
        assert list_page_crop_dirs(tmp_path) == [
            (1, tmp_path / "page_001"),
            (2, tmp_path / "page_002"),
        ]
        assert list_page_crop_dirs(tmp_path / "missing") == []

    def test_crop_display_name_and_paths(self, tmp_path: Path) -> None:
        name = crop_filename(3, 1)
        assert crop_display_name(name) == "page_003_region_01"
        assert crop_display_name(str(tmp_path / name)) == "page_003_region_01"
        assert crop_paths_for(tmp_path, 3, 2) == [
            tmp_path / crop_filename(3, 0),
            tmp_path / crop_filename(3, 1),
        ]

    def test_propose_does_not_write_regions_ink(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "page.png", (40, 40), (255, 255, 255))
        proposer = FakeProposer(region=Region(x=0, y=0, width=20, height=20), question_number=0)
        regions, source, json_path = make_recognizer(tmp_path, proposer=proposer).propose_page_crops(image, 1)
        assert source == "ink"
        assert len(regions) == 1
        assert json_path.is_file()
        assert (tmp_path / "crops" / "page_001" / "page_001_region_00_solution.png").is_file()
        assert not (tmp_path / "crops" / "page_001" / "page_001_regions_ink.json").exists()

    def test_recrop_from_edited_json(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "page.png", (100, 100), (255, 255, 255))
        recognizer = make_recognizer(tmp_path)
        page_dir = tmp_path / "crops" / "page_001"
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
        crop_a = page_dir / "page_001_region_00_solution.png"
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

    @pytest.mark.parametrize(
        ("page_number", "index", "expected"),
        [
            (1, 0, "page_001_region_00_solution.png"),
            (12, 3, "page_012_region_03_solution.png"),
        ],
    )
    def test_crop_filename_includes_page_number(
        self, page_number: int, index: int, expected: str
    ) -> None:
        assert crop_filename(page_number, index) == expected

    def test_crop_filename_rejects_invalid_page(self) -> None:
        with pytest.raises(ValueError):
            crop_filename(0, 0)

    def test_recrop_removes_legacy_crop_names(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "page.png", (40, 40), (255, 255, 255))
        page_dir = tmp_path / "crops" / "page_002"
        write_regions_artifact(
            page_dir,
            2,
            regions=[
                DetectedRegion(
                    type="solution",
                    region=Region(x=0, y=0, width=10, height=10),
                    order=0,
                )
            ],
            source="ink",
        )
        legacy = write_png(page_dir / "region_00_solution.png", (5, 5), (0, 0, 0))
        make_recognizer(tmp_path).recrop_page_from_json(image, 2)
        assert not legacy.exists()
        assert sorted(p.name for p in page_dir.glob("*.png")) == [
            "page_002_region_00_solution.png"
        ]


class TestCropEnsure:

    class _NoRender:
        def render(self, pdf_path, pages_dir, dpi):
            raise AssertionError("render should not run")

    def test_crop_controller_accepts_crop_workspace_port(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        write_png(pages_dir / "page_001.png", (20, 20), (255, 255, 255))
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

            def save_page_regions(self, image_path, page_number, regions, *, source):
                raise AssertionError("unused")

        class _FakeRenderer:
            def render(self, pdf_path, pages_dir, dpi):
                raise AssertionError("unused")

        controller = CropController(renderer=_FakeRenderer(), workspace=_FakeCrop())
        pages = [Page(page_number=1, width=20, height=20, image="page_001.png")]
        result = controller.ensure_crops(pages, pages_dir)
        assert len(result.pages) == 1
        assert result.pages[0].json_path.is_file()

    class _RecordingCrop(CropWorkspace):
        """Workspace that writes one region per proposed page and records the page numbers."""

        def __init__(self, crops: Path) -> None:
            self._crops = crops
            self.proposed: list[int] = []

        @property
        def crops_dir(self) -> Path:
            return self._crops

        def page_crop_dir(self, page_number: int) -> Path:
            return self._crops / f"page_{page_number:03d}"

        def propose_page_crops(self, image_path: Path, page_number: int):
            self.proposed.append(page_number)
            regions = [
                DetectedRegion(type="solution", region=Region(x=0, y=0, width=10, height=10), order=0)
            ]
            path = write_regions_artifact(
                self.page_crop_dir(page_number), page_number, regions=regions, source="ink"
            )
            return regions, "ink", path

        def recrop_page_from_json(self, image_path: Path, page_number: int):
            raise AssertionError("recrop should not run")

        def save_page_regions(self, image_path, page_number, regions, *, source):
            raise AssertionError("save should not run")

    def test_use_existing_proposes_only_pages_without_json(self, tmp_path: Path) -> None:
        workspace = self._RecordingCrop(tmp_path / "crops")
        _write_regions(workspace.crops_dir, 1, 2)
        edited = regions_json_path(workspace.page_crop_dir(1), 1)
        before = edited.read_bytes()
        controller = CropController(renderer=self._NoRender(), workspace=workspace)
        pages = [
            Page(page_number=n, width=20, height=20, image=f"page_{n:03d}.png") for n in (1, 2)
        ]
        result = controller.ensure_crops(pages, tmp_path / "pages", use_existing=True)
        assert workspace.proposed == [2]
        assert edited.read_bytes() == before
        assert [(s.page_number, len(s.crop_paths)) for s in result.pages] == [(1, 2), (2, 1)]

    @pytest.mark.parametrize(
        ("regions", "error_cls"),
        [(None, RegionsArtifactMissingError), ([], EmptyRegionsError)],
        ids=["missing_json", "empty_regions"],
    )
    def test_recrop_page_errors_are_domain_errors(
        self, tmp_path: Path, regions, error_cls
    ) -> None:
        recognizer = make_recognizer(tmp_path)
        image = write_png(tmp_path / "pages" / "page_001.png", (20, 20))
        if regions is not None:
            write_regions_artifact(
                recognizer.page_crop_dir(1), 1, regions=regions, source="ink"
            )
        with pytest.raises(error_cls) as info:
            recognizer.recrop_page_from_json(image, 1)
        assert isinstance(info.value, MathGraderError)

    def test_ensure_crops_proposes_every_page(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        write_png(pages_dir / "page_001.png", (40, 40))
        proposer = FakeProposer(region=Region(x=0, y=0, width=15, height=15), question_number=0)
        recognizer = make_recognizer(tmp_path, proposer=proposer)

        class _FakeRenderer:
            def render(self, pdf_path, pages_dir, dpi):
                raise AssertionError("unused")

        controller = CropController(renderer=_FakeRenderer(), workspace=recognizer)
        pages = [Page(page_number=1, width=40, height=40, image="page_001.png")]
        result = controller.ensure_crops(pages, pages_dir)
        assert len(result.pages) == 1
        assert result.pages[0].json_path.is_file()


class TestQuestionCrops:

    @staticmethod
    def _hand_edit_orders(crops_dir: Path, page_number: int, orders: list[int]) -> None:
        path = regions_json_path(crops_dir / f"page_{page_number:03d}", page_number)
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item, order in zip(payload["regions"], orders):
            item["order"] = order
        path.write_text(json.dumps(payload), encoding="utf-8")

    @pytest.mark.parametrize(
        ("orders", "expected_indices"),
        [
            ([0, 1, 2, 3, 4, 5, 4], [0, 1, 2, 3, 4, 5, 6]),
            ([0, 1, 2, 3, 4, 6, 5], [0, 1, 2, 3, 4, 6, 5]),
            ([10, 30, 20, 40, 50, 60, 70], [0, 2, 1, 3, 4, 5, 6]),
        ],
    )
    def test_reading_order_follows_normalized_region_order(
        self, tmp_path: Path, orders: list[int], expected_indices: list[int]
    ) -> None:
        names = _write_regions(tmp_path, 1, 7)
        self._hand_edit_orders(tmp_path, 1, orders)
        refs = list_crops_in_reading_order(tmp_path)
        assert [r.name for r in refs] == [names[i] for i in expected_indices]
        assert sorted(r.order for r in refs) == list(range(7))

    def test_reading_order_spans_pages(self, tmp_path: Path) -> None:
        page2 = _write_regions(tmp_path, 2, 1)
        page1 = _write_regions(tmp_path, 1, 2)
        refs = list_crops_in_reading_order(tmp_path)
        assert [r.name for r in refs] == page1 + page2
        assert list_crops_in_reading_order(tmp_path / "missing") == []

    def test_carry_forward_within_and_across_pages(self, tmp_path: Path) -> None:
        a, b, c = _write_regions(tmp_path, 1, 3)
        (d,) = _write_regions(tmp_path, 2, 1)
        crops = list_crops_in_reading_order(tmp_path)
        mapping = assign_by_labels(crops, {a: [1], c: [2]}, [1, 2, 3])
        assert mapping == {1: [a, b], 2: [c, d], 3: []}

    def test_unlabeled_leading_crop_is_left_out(self, tmp_path: Path) -> None:
        a, b = _write_regions(tmp_path, 1, 2)
        crops = list_crops_in_reading_order(tmp_path)
        assert assign_by_labels(crops, {b: [1]}, [1]) == {1: [b]}

    def test_one_crop_two_questions_carries_last(self, tmp_path: Path) -> None:
        a, b = _write_regions(tmp_path, 1, 2)
        crops = list_crops_in_reading_order(tmp_path)
        mapping = assign_by_labels(crops, {a: [1, 2, 9]}, [1, 2])
        assert mapping == {1: [a], 2: [a, b]}
        assert crop_to_questions(mapping) == {a: [1, 2], b: [2]}

    def test_sequential_only_when_counts_match(self, tmp_path: Path) -> None:
        names = _write_regions(tmp_path, 1, 3)
        crops = list_crops_in_reading_order(tmp_path)
        assert assign_sequential(crops, [3, 1, 2]) == {1: [names[0]], 2: [names[1]], 3: [names[2]]}
        assert assign_sequential(crops, [1, 2]) == {1: [], 2: []}

    def test_write_load_roundtrip_drops_stale_files(self, tmp_path: Path) -> None:
        stale = question_crops_path(tmp_path, 9)
        stale.parent.mkdir(parents=True)
        stale.write_text("{}", encoding="utf-8")
        paths = write_question_crops(tmp_path, {1: ["x.png"], 2: []}, stems={1: "soal satu"})
        assert [p.name for p in paths] == ["question_001.json", "question_002.json"]
        assert not stale.exists()
        payload = json.loads(paths[0].read_text(encoding="utf-8"))
        assert payload == {"question_number": 1, "stem": "soal satu", "crops": ["x.png"]}
        assert load_question_crops(tmp_path) == {1: ["x.png"], 2: []}

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_question_crops(tmp_path) is None

    @pytest.mark.parametrize(
        "content",
        ["{not json", '{"question_number": 0, "crops": []}'],
        ids=["malformed", "invalid_number"],
    )
    def test_load_rejects_bad_file(self, tmp_path: Path, content: str) -> None:
        path = question_crops_path(tmp_path, 1)
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="question_001.json"):
            load_question_crops(tmp_path)

    def test_load_rejects_duplicate_number(self, tmp_path: Path) -> None:
        write_question_crops(tmp_path, {1: []})
        dup = question_crops_dir(tmp_path) / "question_002.json"
        dup.write_text('{"question_number": 1, "crops": []}', encoding="utf-8")
        with pytest.raises(ValueError, match="appears twice"):
            load_question_crops(tmp_path)

    def test_validate_errors_and_warnings(self) -> None:
        report = validate_question_crops(
            {1: ["a.png"], 2: [], 8: ["ghost.png"]},
            [1, 2, 3],
            ["a.png", "b.png"],
        )
        assert not report.ok
        assert report.errors == [
            "soal 8 tidak ada di kunci",
            "soal 8: crop tidak ditemukan: ghost.png",
        ]
        assert report.missing_questions == [2, 3]
        assert report.unassigned_crops == ["b.png"]

    def test_labeler_filters_numbers_to_schema(self, tmp_path: Path) -> None:
        client = FakeClient('{"question_numbers": [2, 9, "2", "x", 3]}')
        labeler = OllamaQuestionLabeler(client=client, model="vision-test", exam_schema=_schema(3))
        assert labeler.detect(tmp_path / "crop.png") == [2, 3]
        prompt, _path, model = client.calls[0]
        assert "{{expected_questions}}" not in prompt
        assert model == "vision-test"

    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ("no json here", None),
            ('{"labels": [1]}', None),
            ('{"question_numbers": []}', []),
        ],
        ids=["bad-json", "no-number-list", "continuation"],
    )
    def test_labeler_separates_unreadable_from_continuation(
        self, tmp_path: Path, reply: str, expected: list[int] | None
    ) -> None:
        labeler = OllamaQuestionLabeler(
            client=FakeClient(reply), model="vision-test", exam_schema=_schema(3)
        )
        assert labeler.detect(tmp_path / "crop.png") == expected


class TestQuestionLabelController:

    def test_label_all_writes_one_file_per_question(self, tmp_path: Path) -> None:
        p1 = _write_regions(tmp_path, 1, 4)
        p2 = _write_regions(tmp_path, 2, 4)
        labeler = _FakeLabeler(
            {p1[0]: [1], p1[1]: [2], p1[3]: [3, 4], p2[1]: [5], p2[2]: [6], p2[3]: [7]}
        )
        controller = QuestionLabelController(
            crops_dir=tmp_path, exam_schema=_schema(7), labeler=labeler
        )
        result = controller.label_all()
        assert result.source == "vision"
        assert result.report.ok
        assert len(labeler.seen) == 8
        assert labeler.seen[0] == tmp_path / "page_001" / p1[0]
        assert result.mapping == {
            1: [p1[0]],
            2: [p1[1], p1[2]],
            3: [p1[3]],
            4: [p1[3], p2[0]],
            5: [p2[1]],
            6: [p2[2]],
            7: [p2[3]],
        }
        files = sorted(controller.json_dir.glob("question_*.json"))
        assert len(files) == 7
        assert json.loads(files[0].read_text(encoding="utf-8"))["stem"] == "soal 1"
        assert load_question_crops(tmp_path) == result.mapping

    def test_label_all_reports_unreadable_labels(self, tmp_path: Path) -> None:
        names = _write_regions(tmp_path, 1, 3)
        labeler = _FakeLabeler({names[0]: [1], names[1]: None, names[2]: [2]})
        result = QuestionLabelController(
            crops_dir=tmp_path, exam_schema=_schema(2), labeler=labeler
        ).label_all()
        assert result.source == "vision"
        assert result.mapping == {1: [names[0], names[1]], 2: [names[2]]}
        assert result.report.ok
        assert result.report.unreadable_crops == [names[1]]

    def test_label_all_without_labeler_is_sequential(self, tmp_path: Path) -> None:
        names = _write_regions(tmp_path, 1, 2)
        result = QuestionLabelController(crops_dir=tmp_path, exam_schema=_schema(2)).label_all()
        assert result.source == "sequential"
        assert result.mapping == {1: [names[0]], 2: [names[1]]}

    def test_label_all_count_mismatch_leaves_lists_empty(self, tmp_path: Path) -> None:
        _write_regions(tmp_path, 1, 3)
        result = QuestionLabelController(crops_dir=tmp_path, exam_schema=_schema(2)).label_all()
        assert result.mapping == {1: [], 2: []}
        assert result.report.missing_questions == [1, 2]

    def test_label_all_requires_regions(self, tmp_path: Path) -> None:
        with pytest.raises(NoRegionsForLabelingError):
            QuestionLabelController(crops_dir=tmp_path, exam_schema=_schema(1)).label_all()

    def test_reload_all_reports_broken_regions_json(self, tmp_path: Path) -> None:
        _write_regions(tmp_path, 1, 1)
        write_question_crops(tmp_path, {1: [crop_filename(1, 0)]})
        regions_json_path(tmp_path / "page_001", 1).write_text("{broken", encoding="utf-8")
        result = QuestionLabelController(crops_dir=tmp_path, exam_schema=_schema(1)).reload_all()
        assert not result.report.ok
        assert result.mapping == {}

    def test_reading_order_skips_page_zero_folder(self, tmp_path: Path) -> None:
        names = _write_regions(tmp_path, 1, 1)
        (tmp_path / "page_000").mkdir()
        assert [r.name for r in list_crops_in_reading_order(tmp_path)] == names

    def test_reload_all_without_folder_reports_error(self, tmp_path: Path) -> None:
        _write_regions(tmp_path, 1, 1)
        result = QuestionLabelController(crops_dir=tmp_path, exam_schema=_schema(1)).reload_all()
        assert result.mapping == {}
        assert result.source is LabelSource.RELOAD
        assert "halaman Label" in result.report.errors[0]

    def test_invalid_mapping_is_logged_not_printed(self, tmp_path: Path, caplog, capsys) -> None:
        _write_regions(tmp_path, 1, 1)
        with caplog.at_level(logging.INFO, logger="app.controllers.question_label_controller"):
            QuestionLabelController(crops_dir=tmp_path, exam_schema=_schema(1)).reload_all()
        assert "1 error(s)" in caplog.text
        assert capsys.readouterr() == ("", "")

    def test_factory_reads_schema_from_topic_folder(self, tmp_path: Path) -> None:
        standard = q1_standard(tmp_path)
        config = AppConfig(grading=GradingConfig(standards_root=standard.parent))
        crops = tmp_path / "crops"
        controller = build_question_label_controller(config, crops, topic_id="1.5")
        assert controller.json_dir == question_crops_dir(crops)
        with pytest.raises(ExamSchemaMissingError, match="topik_2"):
            build_question_label_controller(config, crops, topic_id="2")


class TestRecognizerQuestionCrops:

    def _recognize(self, tmp_path: Path, content, *, regions: int = 2):
        image = write_png(tmp_path / "pages" / "page_001.png", (40, 40), (255, 255, 255))
        names = _write_regions(tmp_path / "crops", 1, regions)
        client = FakeClient(content)
        recognizer = make_recognizer(tmp_path, client, exam_schema=_schema(7))
        return names, client, (lambda: recognizer.recognize_page_from_crops(image, 1))

    def test_single_assigned_number_is_forced(self, tmp_path: Path) -> None:
        names, _client, run = self._recognize(tmp_path, single_question_json(5, "x < 1"), regions=1)
        write_question_crops(tmp_path / "crops", {2: [names[0]]})
        (question,) = run().questions
        assert question.question_number == 2
        assert not question.review_required

    def test_multiple_assigned_numbers_restrict_model(self, tmp_path: Path) -> None:
        payload = json.dumps(
            {
                "questions": [
                    json.loads(single_question_json(1, "x < 1")),
                    json.loads(single_question_json(3, "x > 2")),
                ]
            }
        )
        names, client, run = self._recognize(tmp_path, payload, regions=1)
        write_question_crops(tmp_path / "crops", {1: [names[0]], 2: [names[0]]})
        page = run()
        assert [q.question_number for q in page.questions] == [1, 0]
        assert page.questions[1].review_required
        assert "not in assigned 1,2" in page.questions[1].reconcile_note
        assert "This crop contains exam questions 1, 2" in client.calls[0][0]

    def test_question_spanning_crops_is_not_demoted(self, tmp_path: Path) -> None:
        names, _client, run = self._recognize(tmp_path, single_question_json(1, "x < 1"))
        write_question_crops(tmp_path / "crops", {1: names})
        page = run()
        assert [q.question_number for q in page.questions] == [1, 1]
        assert not any(q.review_required for q in page.questions)

    def test_without_question_crops_falls_back_to_model(self, tmp_path: Path) -> None:
        _names, client, run = self._recognize(tmp_path, single_question_json(1, "x < 1"))
        page = run()
        assert [q.question_number for q in page.questions] == [1, 0]
        assert "duplicate_of=1" in page.questions[1].reconcile_note
        assert "This crop contains" not in client.calls[0][0]


def _box(x: float, y: float, width: float, height: float, **extra) -> dict:
    return {"x": x, "y": y, "width": width, "height": height, **extra}


class TestManualRegionEditor:

    def test_manual_boxes_get_no_padding(self) -> None:
        assert crop_padding_for(MANUAL_REGION_SOURCE) == CropPadding(pad_ratio=0.0, min_pad=0)
        ink = crop_padding_for("ink")
        assert ink.pad_ratio > 0 and ink.min_pad > 0

    @pytest.mark.parametrize(
        ("box", "message"),
        [
            (Region(x=10, y=10, width=3, height=50), "minimal 4 px"),
            (Region(x=-5, y=0, width=20, height=20), "di luar halaman"),
            (Region(x=190, y=0, width=20, height=20), "di luar halaman"),
            (Region(x=0, y=290, width=20, height=20), "di luar halaman"),
        ],
        ids=["too-small", "left", "right", "bottom"],
    )
    def test_manual_region_errors(self, box: Region, message: str) -> None:
        regions = [DetectedRegion(type="solution", region=box, order=0)]
        (error,) = manual_region_errors(regions, image_width=200, image_height=300)
        assert message in error

    def test_manual_region_errors_accept_edge_boxes_and_need_one(self) -> None:
        edge = DetectedRegion(type="solution", region=Region(x=0, y=0, width=200.5, height=300), order=0)
        assert manual_region_errors([edge], image_width=200, image_height=300) == []
        assert manual_region_errors([], image_width=200, image_height=300)

    def test_recognizer_crops_manual_box_exactly(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "pages" / "page_001.png", (100, 80), (255, 255, 255))
        recognizer = make_recognizer(tmp_path)
        box = DetectedRegion(type="solution", region=Region(x=10, y=5, width=30, height=20), order=0)
        regions, source, json_path = recognizer.save_page_regions(
            image, 1, [box], source=MANUAL_REGION_SOURCE
        )
        assert source == MANUAL_REGION_SOURCE
        assert load_regions_artifact(json_path)[1] == MANUAL_REGION_SOURCE
        crop = recognizer.page_crop_dir(1) / crop_filename(1, 0)
        with Image.open(crop) as img:
            assert img.size == (30, 20)
        with pytest.raises(EmptyRegionsError):
            recognizer.save_page_regions(image, 1, [], source=MANUAL_REGION_SOURCE)

    def test_controller_rejects_invalid_boxes_before_writing(self, tmp_path: Path) -> None:
        pages = write_run_pages(tmp_path / "pages", (200, 300))
        recognizer = make_recognizer(tmp_path)
        controller = CropController(renderer=object(), workspace=recognizer)
        outside = DetectedRegion(type="solution", region=Region(x=150, y=0, width=100, height=10), order=0)
        with pytest.raises(InvalidRegionsError, match="di luar halaman"):
            controller.save_page_regions(pages[0].page_number, [outside], tmp_path / "pages")
        assert not recognizer.page_crop_dir(1).exists()

    def test_editor_page_and_empty_regions(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        web.run_dir("answer", (200, 300), (200, 300))
        page = web.client.get("/runs/answer/crops", params={"page": 2})
        assert page.status_code == 200
        assert_contains(page.text, "cropEditor(", "konva.min.js", "/runs/answer/pages/2/image")
        assert page.text.count("${savedCount} kotak") == 1
        regions = web.client.get("/api/runs/answer/pages/1/regions").json()
        assert regions["page"]["regions"] == [] and regions["crop_names"] == []
        assert web.client.get("/runs/answer/crops", params={"page": 3}).status_code == 404

    def test_put_regions_recrops_in_order(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        layout = web.run_dir("answer", (200, 300))
        body = {"regions": [_box(10, 150, 60, 40, question_number=2), _box(10, 20, 80, 50)]}
        response = web.client.put("/api/runs/answer/pages/1/regions", json=body)
        assert response.status_code == 200, response.text
        out = response.json()
        assert out["page"]["source"] == MANUAL_REGION_SOURCE
        assert [r["question_number"] for r in out["page"]["regions"]] == [2, 0]
        assert out["crop_names"] == [crop_filename(1, 0), crop_filename(1, 1)]
        with Image.open(layout.crops_dir / "page_001" / crop_filename(1, 0)) as img:
            assert img.size == (60, 40)
        thumbs = web.client.get("/runs/answer/pages/1/thumbs").text
        assert_contains(thumbs, crop_filename(1, 0), "soal 2")
        image = web.client.get(f"/runs/answer/crops/{crop_filename(1, 1)}")
        assert image.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize(
        ("regions", "needle"),
        [
            ([_box(10, 10, 2, 2)], "minimal 4 px"),
            ([], "kotak"),
            ([_box(10, 10, 20, 20, question_number=-1)], "question_number"),
        ],
        ids=["tiny", "empty", "negative-number"],
    )
    def test_put_invalid_regions_is_422_json(
        self, tmp_path: Path, monkeypatch, regions: list[dict], needle: str
    ) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        layout = web.run_dir("answer", (200, 300))
        response = web.client.put("/api/runs/answer/pages/1/regions", json={"regions": regions})
        assert response.status_code == 422
        assert needle in json.dumps(response.json()["detail"])
        assert not (layout.crops_dir / "page_001").exists()

    def test_run_without_pages_has_no_editor(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        (web.output_root / "answer" / "crops").mkdir(parents=True)
        response = web.client.get("/runs/answer/crops")
        assert response.status_code == 404
        assert "Propose crops" in response.text


class TestWebLabels:

    @pytest.mark.parametrize(
        ("form", "expected"),
        [
            ({"crop:a.png": "1, 2", "crop:b.png": "", "other": "x"}, {"a.png": [1, 2], "b.png": []}),
            ({"crop:a.png": " 3;4  5 "}, {"a.png": [3, 4, 5]}),
        ],
    )
    def test_parse_crop_labels(self, form: dict, expected: dict) -> None:
        assert parse_crop_labels(form) == expected

    @pytest.mark.parametrize("raw", ["x", "0", "-1", "1.5"])
    def test_parse_crop_labels_rejects_non_numbers(self, raw: str) -> None:
        with pytest.raises(QuestionCropsInvalidError):
            parse_crop_labels({"crop:a.png": raw})

    def test_mapping_from_crop_labels(self, tmp_path: Path) -> None:
        names = _write_regions(tmp_path, 1, 3)
        crops = list_crops_in_reading_order(tmp_path)
        labels = {names[0]: [1, 1], names[1]: [2, 9], names[2]: []}
        assert mapping_from_crop_labels(crops, labels, [1, 2, 3]) == {
            1: [names[0]],
            2: [names[1]],
            3: [],
            9: [names[1]],
        }

    def _labeled_run(self, web: WebHarness) -> tuple[Path, list[str]]:
        web.standard()
        layout = web.run_dir("answer")
        return layout.crops_dir, _write_regions(layout.crops_dir, 1, 2)

    def test_labels_page_lists_crops_and_questions(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        _crops, names = self._labeled_run(web)
        page = web.client.get("/runs/answer/labels")
        assert page.status_code == 200
        assert_contains(page.text, f'name="crop:{names[0]}"', f'name="crop:{names[1]}"', "2-3x")

    def test_htmx_save_returns_the_form_with_report(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        crops, names = self._labeled_run(web)
        response = web.htmx(
            "POST", "/runs/answer/labels", data={f"crop:{names[0]}": "1", f"crop:{names[1]}": ""}
        )
        assert response.status_code == 200
        assert_contains(response.text, 'id="label-form"', "Nomor soal disimpan", "1 crop tanpa nomor soal")
        assert load_question_crops(crops) == {1: [names[0]]}

    def test_plain_save_redirects(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        _crops, names = self._labeled_run(web)
        response = web.client.post("/runs/answer/labels", data={f"crop:{names[0]}": "1"})
        assert response.status_code == 303
        assert response.headers["location"].startswith("/runs/answer/labels?ok=")

    def test_bad_label_is_a_flash(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        crops, names = self._labeled_run(web)
        response = web.htmx("POST", "/runs/answer/labels", data={f"crop:{names[0]}": "satu"})
        assert response.status_code == 422
        assert response.headers["HX-Retarget"] == "#flash"
        assert load_question_crops(crops) is None

    def test_labels_need_an_ingested_kunci(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        _write_regions(web.run_dir("answer").crops_dir, 1, 1)
        assert web.client.get("/runs/answer/labels").status_code == 422

    def test_detect_job_without_vision_assigns_in_order(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch, vision_model="")
        web.standard()
        crops = web.run_dir("answer").crops_dir
        names = _write_regions(crops, 1, 1)
        job = web.job(web.client.post("/runs/answer/labels/detect"))
        assert job.status == JobStatus.DONE, job.error
        assert job.next_url == "/runs/answer/labels"
        assert load_question_crops(crops) == {1: names}


class TestWebReview:

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("3*x - 5 < 4*x - 6", "3 x - 5 < 4 x - 6"), ("", None), ("((", None)],
        ids=["relation", "empty", "unparseable"],
    )
    def test_symbolic_preview_latex(self, text: str, expected: str | None) -> None:
        assert symbolic_preview_latex(text) == expected

    def test_preview_endpoint(self, tmp_path: Path, monkeypatch) -> None:
        client = WebHarness(tmp_path, monkeypatch).client
        assert client.post("/api/preview", json={"text": "x >= 2"}).json() == {"latex": "x \\geq 2"}
        assert client.post("/api/preview", json={"text": "x" * 2001}).status_code == 422

    def _reviewed_run(self, web: WebHarness) -> Path:
        layout = web.run_dir("answer")
        question = make_question(steps=[make_step(1, symbolic_repr="2 - 3*x <= 12", raw_text="2-3x<=12")])
        return write_question_dir(layout.questions_dir, question)

    def test_review_page_lists_questions(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        self._reviewed_run(web)
        page = web.client.get("/runs/answer/review")
        assert page.status_code == 200
        assert_contains(page.text, "questionEditor(", "question_001", "/api/runs/answer/questions/question_001")

    def test_put_question_saves_the_edit(self, tmp_path: Path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        path = self._reviewed_run(web)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["student_steps"][0]["symbolic"]["repr"] = "2 - 3*x < 12"
        response = web.client.put("/api/runs/answer/questions/question_001", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["edited_ids"] == ["question_001"]
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["student_steps"][0]["symbolic"]["repr"] == "2 - 3*x < 12"

    @pytest.mark.parametrize(
        ("question_id", "change", "needle"),
        [
            ("question_001", {"student_steps": "nope"}, "student_steps"),
            ("question_002", {}, "tidak ada"),
        ],
        ids=["invalid-shape", "unknown-question"],
    )
    def test_put_invalid_question_is_422(
        self, tmp_path: Path, monkeypatch, question_id: str, change: dict, needle: str
    ) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        path = self._reviewed_run(web)
        before = path.read_text(encoding="utf-8")
        payload = {**json.loads(before), **change}
        response = web.client.put(f"/api/runs/answer/questions/{question_id}", json=payload)
        assert response.status_code == 422
        assert needle in response.json()["detail"]
        assert path.read_text(encoding="utf-8") == before
