"""Tests for solution-crop helpers and two-pass recognition (no live Ollama)."""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image
from app.functions.image_crop import (
    clamp_region,
    crop_region,
    expand_region,
    normalize_region_to_pixels,
    prepare_crop_region,
    union_regions,
)
from app.functions.ink_layout import InkLayoutParams, propose_solution_regions_from_image
from app.functions.kunci_ingest import format_recognition_stems_block
from app.functions.question_merge import collect_latex_documents, merge_page_recognitions
from app.models.recognition import (
    DetectedRegion,
    PageRecognition,
    RecognizedQuestion,
    RecognizedStep,
    Region,
    SymbolicPayload,
)
from app.services.vision.ink_region_proposer import InkRegionProposer
from app.services.vision.recognizer import OllamaVisionRecognizer


class TestCropHelpers:

    def test_normalize_fractional_region(self) -> None:
        region = Region(x=0.1, y=0.2, width=0.5, height=0.4)
        pixel = normalize_region_to_pixels(region, image_width=200, image_height=100)
        assert pixel.x == 20
        assert pixel.y == 20
        assert pixel.width == 100
        assert pixel.height == 40

    def test_expand_and_prepare_crop_region(self) -> None:
        region = Region(x=50, y=50, width=40, height=30)
        expanded = expand_region(
            region, image_width=200, image_height=200, pad_ratio=0.05, min_pad=8
        )
        assert expanded.x < region.x
        assert expanded.y < region.y
        assert expanded.width > region.width
        prepared = prepare_crop_region(
            Region(x=0.25, y=0.25, width=0.2, height=0.2),
            image_width=100,
            image_height=100,
            pad_ratio=0.0,
            min_pad=0,
        )
        assert prepared.x == 25
        assert prepared.width == 20

    def test_union_regions(self) -> None:
        a = Region(x=10, y=10, width=20, height=20)
        b = Region(x=25, y=15, width=30, height=40)
        united = union_regions([a, b])
        assert united is not None
        assert united.x == 10
        assert united.y == 10
        assert united.width == 45
        assert united.height == 45

    def test_clamp_and_crop_region(self, tmp_path: Path) -> None:
        image_path = tmp_path / "page.png"
        Image.new("RGB", (100, 80), color=(255, 255, 255)).save(image_path)
        region = Region(x=10, y=10, width=40, height=30)
        out = tmp_path / "crop.png"
        result = crop_region(image_path, region, out, pad_ratio=0.0, min_pad=0)
        assert result.path == out
        assert result.used_full_page_fallback is False
        assert out.is_file()
        with Image.open(out) as cropped:
            assert cropped.size == (40, 30)

        clamped = clamp_region(
            Region(x=-5, y=-5, width=200, height=200),
            image_width=100,
            image_height=80,
        )
        assert clamped.x == 0 and clamped.y == 0
        assert clamped.width == 100 and clamped.height == 80


class TestSymbolicMerge:

    def test_merge_symbolic_and_inline_figures(self) -> None:
        pages = [
            PageRecognition(
                page_number=1,
                questions=[
                    RecognizedQuestion(
                        question_number=1,
                        region_type="solution",
                        crop_path="crops/s.png",
                        steps=[
                            RecognizedStep(
                                step_number=1,
                                raw_text="2x-3<5",
                                latex="",
                                symbolic=SymbolicPayload(kind="relation", repr="2*x-3<5"),
                                role="algebra",
                            ),
                            RecognizedStep(
                                step_number=2,
                                raw_text="number line",
                                latex="",
                                symbolic=SymbolicPayload(
                                    kind="figure",
                                    repr="NUMBER_LINE((1,oo))",
                                ),
                                role="figure",
                            ),
                            RecognizedStep(
                                step_number=3,
                                raw_text="x<4",
                                latex="",
                                symbolic=SymbolicPayload(kind="relation", repr="x<4"),
                                role="hp",
                            ),
                        ],
                        final_answer="x<4",
                        final_answer_symbolic=SymbolicPayload(kind="relation", repr="x<4"),
                        latex_document=r"\begin{aligned}2x-3<5\end{aligned}",
                    ),
                ],
            )
        ]
        questions = merge_page_recognitions(pages)
        assert len(questions) == 1
        q = questions[0]
        assert len(q.student_steps) == 2
        assert q.student_steps[0].latex == ""
        assert q.student_steps[0].role == "algebra"
        assert q.student_steps[1].role == "hp"
        assert len(q.figure_refs) == 1
        assert q.figure_refs[0].caption == "number line"
        assert q.figure_refs[0].symbolic is not None
        assert q.figure_refs[0].symbolic.repr == "NUMBER_LINE((1,oo))"
        assert collect_latex_documents(pages)[1]

    def test_figure_crop_uses_figure_step_not_leading_algebra(self) -> None:
        pages = [
            PageRecognition(
                page_number=1,
                questions=[
                    RecognizedQuestion(
                        question_number=1,
                        region_type="figure",
                        crop_path="crops/fig.png",
                        steps=[
                            RecognizedStep(
                                step_number=1,
                                raw_text="x > 1",
                                latex="",
                                symbolic=SymbolicPayload(kind="relation", repr="x > 1"),
                                role="algebra",
                            ),
                            RecognizedStep(
                                step_number=2,
                                raw_text="open ray from 1",
                                latex="",
                                symbolic=SymbolicPayload(
                                    kind="figure",
                                    repr="NUMBER_LINE((1,oo))",
                                ),
                                role="figure",
                            ),
                        ],
                    ),
                ],
            )
        ]
        questions = merge_page_recognitions(pages)
        assert len(questions) == 1
        refs = questions[0].figure_refs
        assert len(refs) == 1
        assert refs[0].symbolic is not None
        assert refs[0].symbolic.repr == "NUMBER_LINE((1,oo))"
        assert refs[0].caption == "open ray from 1"

    def test_coalesce_step_role_infers_from_text(self) -> None:
        from app.functions.step_role import coalesce_step_role
        from app.models.recognition import SymbolicPayload

        assert coalesce_step_role("x>1", SymbolicPayload(kind="relation", repr="x>1"), None) == "algebra"
        assert (
            coalesce_step_role(
                "number line",
                SymbolicPayload(kind="figure", repr=""),
                None,
            )
            == "figure"
        )
        assert coalesce_step_role("HP = (1, oo)", None, None) == "hp"
        assert coalesce_step_role("HP = (1, oo)", None, "algebra") == "hp"
        assert coalesce_step_role("Jadi HP = (-1,1)", None, None) == "hp"
        assert coalesce_step_role("Jadi (-1,1)", None, None) == "hp"
        assert coalesce_step_role(r"x \in (-1,1)", None, "algebra") == "hp"
        assert (
            coalesce_step_role(
                "",
                SymbolicPayload(kind="expression", repr="(-1,1)"),
                None,
            )
            == "hp"
        )
        assert (
            coalesce_step_role(
                "shaded ray",
                SymbolicPayload(kind="relation", repr="NUMBER_LINE((1,oo))"),
                "sign_chart",
            )
            == "figure"
        )
        assert coalesce_step_role("HP = (1, oo)", None, "sign_chart") == "hp"
        assert coalesce_step_role("Titik kritis x=0", None, None) == "critical_points"
        assert coalesce_step_role("x>1", None, "sign_chart") == "sign_chart"
        assert coalesce_step_role("solusi pada selang (-1,1)", None, None) == "algebra"
        assert coalesce_step_role("uji selang x<0", None, "algebra") == "sign_chart"
        # Weak HP must not steal critical-point / mid-prose membership steps.
        assert (
            coalesce_step_role("Jadi titik potong (1, 0)", None, None)
            == "critical_points"
        )
        assert (
            coalesce_step_role(r"ambil x \in (0,1) untuk uji", None, "algebra")
            != "hp"
        )
        assert (
            coalesce_step_role(
                r"x \in (0,1)",
                None,
                "critical_points",
            )
            == "critical_points"
        )

    def test_merge_prefers_last_hp_for_final_answer(self) -> None:
        from app.models.recognition import (
            PageRecognition,
            RecognizedQuestion,
            RecognizedStep,
            SymbolicPayload,
        )

        pages = [
            PageRecognition(
                page_number=1,
                image_path="p1.png",
                questions=[
                    RecognizedQuestion(
                        question_number=1,
                        steps=[
                            RecognizedStep(
                                step_number=1,
                                raw_text=r"x \in (0,1)",
                                role="hp",
                                symbolic=SymbolicPayload(
                                    kind="relation",
                                    repr="0 < x < 1",
                                ),
                            ),
                            RecognizedStep(
                                step_number=2,
                                raw_text="HP = (1/2, oo)",
                                role="hp",
                                symbolic=SymbolicPayload(
                                    kind="relation",
                                    repr="(1/2, oo)",
                                ),
                            ),
                        ],
                        final_answer="",
                    )
                ],
            )
        ]
        questions = merge_page_recognitions(pages)
        assert len(questions) == 1
        assert questions[0].student_final_answer == "(1/2, oo)"
        assert questions[0].student_final_symbolic is not None
        assert questions[0].student_final_symbolic.repr == "(1/2, oo)"

    def test_coalesce_step_symbolic_rebuilds_and_sanitizes(self) -> None:
        from app.functions.symbolic_from_latex import coalesce_step_symbolic
        from app.models.recognition import SymbolicPayload

        rebuilt = coalesce_step_symbolic("2*x - 3 < 5", None)
        assert rebuilt is not None
        assert rebuilt.kind == "relation"
        assert "2" in rebuilt.repr and "<" in rebuilt.repr

        latexish = coalesce_step_symbolic(
            "",
            SymbolicPayload(kind="relation", repr=r"x \leq 4"),
        )
        assert latexish is not None
        assert "\\" not in latexish.repr
        assert "<=" in latexish.repr

        number_line = coalesce_step_symbolic(
            "garis bilangan",
            SymbolicPayload(kind="expression", repr="NUMBER_LINE((1,oo))"),
        )
        assert number_line is not None
        assert number_line.kind == "figure"
        assert number_line.repr == "NUMBER_LINE((1,oo))"

        from_raw_nl = coalesce_step_symbolic("NUMBER_LINE([-2,oo))", None)
        assert from_raw_nl is not None
        assert from_raw_nl.kind == "figure"


class TestTwoPassRecognizer:

    def test_two_pass_recognizer_uses_ink_proposer(self, tmp_path: Path) -> None:
        image_path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), color=(240, 240, 240)).save(image_path)

        math_json = (
            '{"question_number":1,"steps":[{"step_number":1,"raw_text":"2x-3<5",'
            '"symbolic":{"kind":"relation","repr":"2*x-3<5"},"confidence":0.9},'
            '{"step_number":2,"raw_text":"number line",'
            '"symbolic":{"kind":"figure","repr":""},"confidence":0.8}],'
            '"final_answer":"x<4",'
            '"final_answer_symbolic":{"kind":"relation","repr":"x<4"},'
            '"latex_document":"x<4","confidence":0.9}'
        )

        class FakeClient:
            def __init__(self) -> None:
                self.calls = 0

            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                self.calls += 1
                return math_json

        class FakeProposer:
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=10, y=10, width=80, height=90),
                        question_number=1,
                        order=0,
                    )
                ]

        out = tmp_path / "recognition"
        crops = tmp_path / "crops"
        client = FakeClient()
        recognizer = OllamaVisionRecognizer(
            client=client,  # type: ignore[arg-type]
            model="test-model",
            output_dir=out,
            crops_dir=crops,
            proposer=FakeProposer(),  # type: ignore[arg-type]
        )
        page = recognizer.recognize_page(image_path, 1)
        assert len(page.questions) == 1
        assert page.questions[0].region_type == "solution"
        assert page.questions[0].region is not None
        assert page.questions[0].region.width == 80
        assert client.calls == 1  # only crop_math, no LLM detect
        assert list(crops.glob("page_001/*_solution.png"))
        assert (crops / "page_001" / "page_001_regions.json").is_file()
        assert (crops / "page_001" / "region_00_solution.png").is_file()
        assert not (crops / "page_001" / "ink").exists()
        regions = json.loads(
            (crops / "page_001" / "page_001_regions.json").read_text(encoding="utf-8")
        )
        assert regions["regions"][0]["crop_path"] == "region_00_solution.png"
        assert "ink" not in regions
        assert "selected" not in regions
        assert page.prompt_version.startswith("crop-math")
        assert page.model == "test-model"
        assert (out / "page_001_recognition.json").is_file()
        roles = [s.role for s in page.questions[0].steps]
        assert roles[0] == "algebra"
        assert roles[1] == "figure"
        assert page.questions[0].steps[0].latex == ""
        assert page.questions[0].steps[0].symbolic is not None

    def test_recognizer_multi_question_crop_payload(self, tmp_path: Path) -> None:
        """One ink crop returning questions[] expands to two RecognizedQuestion."""
        image_path = tmp_path / "page.png"
        Image.new("RGB", (200, 400), color=(240, 240, 240)).save(image_path)

        multi_json = (
            '{"questions":['
            '{"question_number":6,"steps":[{"step_number":1,"raw_text":"6) a<b",'
            '"symbolic":{"kind":"relation","repr":"a<b"},"confidence":0.9}],'
            '"final_answer":"HP=(-oo,-1)","final_answer_symbolic":'
            '{"kind":"expression","repr":"(-oo,-1)"},"latex_document":"a<b","confidence":0.9},'
            '{"question_number":7,"steps":[{"step_number":1,"raw_text":"7) c<d",'
            '"symbolic":{"kind":"relation","repr":"c<d"},"confidence":0.9}],'
            '"final_answer":"HP=(-4,0)","final_answer_symbolic":'
            '{"kind":"expression","repr":"(-4,0)"},"latex_document":"c<d","confidence":0.9}'
            "]}"
        )

        class FakeClient:
            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                assert "MORE THAN ONE" in prompt or "questions" in prompt
                return multi_json

        class FakeProposer:
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=10, y=10, width=80, height=300),
                        question_number=5,
                        order=0,
                    )
                ]

        out = tmp_path / "recognition"
        crops = tmp_path / "crops"
        recognizer = OllamaVisionRecognizer(
            client=FakeClient(),  # type: ignore[arg-type]
            model="test-model",
            output_dir=out,
            crops_dir=crops,
            proposer=FakeProposer(),  # type: ignore[arg-type]
            expected_questions=[
                (6, r"$\frac{1}{x+1} < \frac{2}{3x-1}$"),
                (7, r"$\frac{x+2}{x+4} < \frac{x-1}{x-2}$"),
            ],
        )
        page = recognizer.recognize_page(image_path, 1)
        assert len(page.questions) == 2
        assert [q.question_number for q in page.questions] == [6, 7]
        crop_paths = {q.crop_path for q in page.questions}
        assert len(crop_paths) == 1
        assert page.questions[0].steps[0].raw_text.startswith("6)")
        assert page.questions[1].steps[0].raw_text.startswith("7)")

    def test_recognizer_single_object_still_one_question(self, tmp_path: Path) -> None:
        """Legacy single-object crop_math JSON still yields one question."""
        image_path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), color=(240, 240, 240)).save(image_path)

        class FakeClient:
            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                return (
                    '{"question_number":1,"steps":[{"step_number":1,"raw_text":"x>0",'
                    '"symbolic":{"kind":"relation","repr":"x>0"},"confidence":0.9}],'
                    '"final_answer":"x>0","final_answer_symbolic":null,'
                    '"latex_document":"x>0","confidence":0.9}'
                )

        class FakeProposer:
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=5, y=5, width=50, height=50),
                        question_number=1,
                        order=0,
                    )
                ]

        recognizer = OllamaVisionRecognizer(
            client=FakeClient(),  # type: ignore[arg-type]
            model="test-model",
            output_dir=tmp_path / "recognition",
            crops_dir=tmp_path / "crops",
            proposer=FakeProposer(),  # type: ignore[arg-type]
        )
        page = recognizer.recognize_page(image_path, 1)
        assert len(page.questions) == 1
        assert page.questions[0].question_number == 1


class TestInkLayout:

    def test_propose_one_column_blocks(self, tmp_path: Path) -> None:
        """Stacked ink blocks with clear gaps → separate regions (single column)."""
        image = Image.new("RGB", (200, 500), color=(255, 255, 255))
        # header zone left mostly blank; blocks below header_fraction
        for y0, y1 in ((60, 120), (160, 220), (280, 360)):
            for y in range(y0, y1):
                for x in range(30, 160):
                    image.putpixel((x, y), (0, 0, 0))
        path = tmp_path / "one_col.png"
        image.save(path)
        params = InkLayoutParams(
            threshold=200,
            merge_gap_ratio=0.02,
            min_block_height_ratio=0.04,
            header_fraction=0.08,
            column_valley_ratio=0.15,
        )
        regions = propose_solution_regions_from_image(image, params=params)
        assert len(regions) == 3
        assert regions[0].y < regions[1].y < regions[2].y
        # No forced second column
        assert all(r.x < 100 for r in regions)

    def test_propose_two_column_blocks(self, tmp_path: Path) -> None:
        """Left and right ink with empty gutter → two columns, reading order L then R."""
        image = Image.new("RGB", (400, 400), color=(255, 255, 255))
        # left column two blocks
        for y0, y1 in ((50, 120), (160, 240)):
            for y in range(y0, y1):
                for x in range(20, 150):
                    image.putpixel((x, y), (0, 0, 0))
        # right column one block
        for y in range(50, 200):
            for x in range(250, 380):
                image.putpixel((x, y), (0, 0, 0))
        params = InkLayoutParams(
            threshold=200,
            merge_gap_ratio=0.02,
            min_block_height_ratio=0.04,
            header_fraction=0.05,
            column_valley_ratio=0.2,
        )
        regions = propose_solution_regions_from_image(image, params=params)
        assert len(regions) >= 3
        # First regions should be left column (smaller x), then right
        leftish = [r for r in regions if r.x + r.width < 200]
        rightish = [r for r in regions if r.x >= 200]
        assert len(leftish) >= 2
        assert len(rightish) >= 1
        # Reading order: left blocks before right
        assert regions[0].x < 200

    def test_ink_region_proposer_assigns_order_without_question_numbers(self, tmp_path: Path) -> None:
        image = Image.new("RGB", (200, 300), color=(255, 255, 255))
        for y in range(50, 120):
            for x in range(20, 160):
                image.putpixel((x, y), (10, 10, 10))
        for y in range(160, 240):
            for x in range(20, 160):
                image.putpixel((x, y), (10, 10, 10))
        path = tmp_path / "page.png"
        image.save(path)
        proposer = InkRegionProposer(
            InkLayoutParams(header_fraction=0.05, min_block_height_ratio=0.05)
        )
        detected = proposer.propose(path, page_number=1)
        assert len(detected) == 2
        assert [d.question_number for d in detected] == [0, 0]
        assert [d.order for d in detected] == [0, 1]

    def test_merge_regions_helper_via_recognizer(self) -> None:
        recognizer = OllamaVisionRecognizer.__new__(OllamaVisionRecognizer)
        regions = [
            DetectedRegion(
                type="solution",
                region=Region(x=0, y=0, width=10, height=10),
                question_number=2,
                order=1,
            ),
            DetectedRegion(
                type="solution",
                region=Region(x=5, y=5, width=10, height=10),
                question_number=2,
                order=2,
            ),
            DetectedRegion(
                type="solution",
                region=Region(x=0, y=50, width=10, height=10),
                question_number=1,
                order=0,
            ),
        ]
        merged = OllamaVisionRecognizer._merge_regions_by_question(recognizer, regions)
        assert len(merged) == 2
        by_q = {m.question_number: m for m in merged}
        assert by_q[2].region.width == 15
        assert by_q[2].region.height == 15


class TestRecognitionStems:

    def test_format_recognition_stems_block(self) -> None:
        assert "no exam key" in format_recognition_stems_block(None).lower()
        block = format_recognition_stems_block(
            [(1, r"$2-3x \le 12$"), (2, r"$3x-5 < 4x-6$")]
        )
        assert "1. $2-3x" in block
        assert "2. $3x-5" in block

    def test_recognizer_injects_stems_and_accepts_expected_qnum(self, tmp_path: Path) -> None:
        image_path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), color=(240, 240, 240)).save(image_path)

        captured: dict[str, str] = {}

        class FakeClient:
            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                captured["prompt"] = prompt
                return (
                    '{"question_number":2,"steps":[{"step_number":1,"raw_text":"x>1",'
                    '"symbolic":{"kind":"relation","repr":"x>1"},"confidence":0.9}],'
                    '"final_answer":"x>1","final_answer_symbolic":null,'
                    '"latex_document":"x>1","confidence":0.9}'
                )

        class FakeProposer:
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=10, y=10, width=80, height=90),
                        question_number=1,  # ink says 1; LLM says 2 (expected)
                        order=0,
                    )
                ]

        stems = [(1, r"$2-3x \le 12$"), (2, r"$3x-5 < 4x-6$")]
        recognizer = OllamaVisionRecognizer(
            client=FakeClient(),  # type: ignore[arg-type]
            model="test-model",
            output_dir=tmp_path / "recognition",
            crops_dir=tmp_path / "crops",
            proposer=FakeProposer(),  # type: ignore[arg-type]
            expected_questions=stems,
        )
        page = recognizer.recognize_page(image_path, 1)
        assert "$2-3x" in captured["prompt"]
        assert "$3x-5" in captured["prompt"]
        # Role instructions may mention "HP"; kunci solutions must not leak into stems.
        after_stems = captured["prompt"].split("Exam question stems", 1)[-1]
        stems_block = after_stems.split("Rules:", 1)[0]
        assert "HP" not in stems_block
        assert page.questions[0].question_number == 2

    def test_recognizer_rejects_out_of_set_qnum(self, tmp_path: Path) -> None:
        image_path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), color=(240, 240, 240)).save(image_path)

        class FakeClient:
            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                return (
                    '{"question_number":99,"steps":[{"step_number":1,"raw_text":"x>1",'
                    '"symbolic":{"kind":"relation","repr":"x>1"},"confidence":0.9}],'
                    '"final_answer":"x>1","final_answer_symbolic":null,'
                    '"latex_document":"x>1","confidence":0.9}'
                )

        class FakeProposer:
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=10, y=10, width=80, height=90),
                        question_number=3,
                        order=0,
                    )
                ]

        recognizer = OllamaVisionRecognizer(
            client=FakeClient(),  # type: ignore[arg-type]
            model="test-model",
            output_dir=tmp_path / "recognition",
            crops_dir=tmp_path / "crops",
            proposer=FakeProposer(),  # type: ignore[arg-type]
            expected_questions=[(1, r"$a$"), (2, r"$b$")],
        )
        page = recognizer.recognize_page(image_path, 1)
        assert page.questions[0].question_number == 3

    def test_recognizer_uses_exam_schema_flags(self, tmp_path: Path) -> None:
        from app.models.exam_schema import ExamPart, ExamQuestion, ExamSchema

        image_path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), color=(240, 240, 240)).save(image_path)
        captured: dict[str, str] = {}

        class FakeClient:
            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                captured["prompt"] = prompt
                return (
                    '{"question_number":1,"steps":[{"step_number":1,"raw_text":"x>0",'
                    '"symbolic":{"kind":"relation","repr":"x>0"},"confidence":0.9}],'
                    '"final_answer":"x>0","final_answer_symbolic":null,'
                    '"latex_document":"x>0","confidence":0.9}'
                )

        class FakeProposer:
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=10, y=10, width=80, height=90),
                        question_number=1,
                        order=0,
                    )
                ]

        schema = ExamSchema(
            source="test",
            questions=[
                ExamQuestion(
                    number=1,
                    stem=r"$x > 0$",
                    steps=["x > 0"],
                    final=r"(0, \infty)",
                    expects_figure=True,
                    parts=[
                        ExamPart(kind="algebra", order=1),
                        ExamPart(kind="figure", order=2),
                        ExamPart(kind="hp", order=3),
                    ],
                )
            ],
        )
        recognizer = OllamaVisionRecognizer(
            client=FakeClient(),  # type: ignore[arg-type]
            model="test-model",
            output_dir=tmp_path / "recognition",
            crops_dir=tmp_path / "crops",
            proposer=FakeProposer(),  # type: ignore[arg-type]
            exam_schema=schema,
        )
        recognizer.recognize_page(image_path, 1)
        assert "[expects_figure]" in captured["prompt"]
        assert r"$x > 0$" in captured["prompt"]
        assert r"(0, \infty)" not in captured["prompt"]

    def test_duplicate_question_kept_as_zero(self, tmp_path: Path) -> None:
        image = Image.new("RGB", (80, 80), color=(255, 255, 255))
        path = tmp_path / "page.png"
        image.save(path)
        math = json.dumps(
            {
                "question_number": 1,
                "steps": [
                    {
                        "step_number": 1,
                        "raw_text": "a",
                        "symbolic": {"kind": "relation", "repr": "x>0"},
                    }
                ],
                "final_answer": "",
                "confidence": 0.5,
            }
        )

        class _FakeClient:
            def __init__(self, contents: list[str]) -> None:
                self._queue = list(contents)

            def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
                if not self._queue:
                    raise AssertionError("unexpected generate_with_image call")
                return self._queue.pop(0)

        class _TwoBoxes(InkRegionProposer):
            def propose(self, image_path: Path, page_number: int = 1):
                return [
                    DetectedRegion(
                        type="solution",
                        region=Region(x=0, y=0, width=30, height=30),
                        question_number=0,
                        order=0,
                    ),
                    DetectedRegion(
                        type="solution",
                        region=Region(x=0, y=40, width=30, height=30),
                        question_number=0,
                        order=1,
                    ),
                ]

        recognizer = OllamaVisionRecognizer(
            client=_FakeClient([math, math]),  # type: ignore[arg-type]
            model="m",
            output_dir=tmp_path / "rec",
            crops_dir=tmp_path / "crops",
            proposer=_TwoBoxes(),
            expected_questions=[(1, "x>0")],
        )
        page = recognizer.recognize_page(path, 1)
        assert len(page.questions) == 2
        numbers = sorted(q.question_number for q in page.questions)
        assert numbers == [0, 1]
        assert page.questions[0].question_number == 1
        assert page.questions[0].region is not None
        assert page.questions[0].region.y == 0
        assert page.review_required is True
        assert page.region_source == "ink"
        page_crops = tmp_path / "crops" / "page_001"
        assert (page_crops / "region_00_solution.png").is_file()
        assert (page_crops / "region_01_solution.png").is_file()
        assert not (page_crops / "ink").exists()
        meta = json.loads(
            (page_crops / "page_001_regions.json").read_text(encoding="utf-8")
        )
        assert meta["regions"][0]["crop_path"] == "region_00_solution.png"
        assert meta["regions"][1]["crop_path"] == "region_01_solution.png"

    def test_malformed_crop_fields_do_not_abort(self, tmp_path: Path) -> None:
        image = tmp_path / "page.png"
        Image.new("RGB", (20, 20), color=(255, 255, 255)).save(image)
        recognizer = OllamaVisionRecognizer(
            client=object(),  # type: ignore[arg-type]
            model="m",
            output_dir=tmp_path / "rec",
            crops_dir=tmp_path / "crops",
        )
        detected = DetectedRegion(
            type="solution",
            region=Region(x=0, y=0, width=10, height=10),
            order=0,
        )
        question = recognizer._recognized_from_payload(  # noqa: SLF001
            {
                "question_number": "1",
                "steps": [
                    {
                        "step_number": "nope",
                        "raw_text": "x>0",
                        "confidence": "high",
                    }
                ],
                "confidence": 4,
            },
            crop_path=tmp_path / "crop.png",
            detected=detected,
        )
        assert question.question_number == 1
        assert question.steps[0].step_number == 1
        assert question.steps[0].confidence is None
        assert question.confidence is None

    def test_empty_crop_fallback_flag(self, tmp_path: Path) -> None:
        image = Image.new("RGB", (50, 50), color=(255, 255, 255))
        path = tmp_path / "p.png"
        image.save(path)
        out = tmp_path / "c.png"
        result = crop_region(
            path,
            Region(x=1000, y=1000, width=1, height=1),
            out,
            pad_ratio=0.0,
            min_pad=0,
        )
        assert result.used_full_page_fallback is True
        assert out.is_file()
