"""Ink propose / Pillow crop / crop_math recognition (ink-only Track A).

Crop boxes are editable via ``page_NNN_regions.json``. Propose writes JSON+PNGs;
recrop reloads JSON; recognize runs crop_math on approved crop PNGs.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.exceptions import (
    EmptyRegionsError,
    InvalidRecognitionJsonError,
    OllamaModelNotConfiguredError,
    RegionsArtifactMissingError,
)
from app.functions.image_crop import crop_region, union_regions
from app.functions.json_extract import coerce_confidence, extract_json_object
from app.functions.kunci_ingest import (
    format_recognition_question_block,
    format_recognition_stems_block,
)
from app.functions.page_names import page_recognition_filename
from app.functions.question_crops import crop_to_questions, load_question_crops
from app.functions.regions_artifact import (
    crop_filename,
    load_regions_artifact,
    page_has_regions_artifact,
    regions_json_path,
    write_regions_artifact,
)
from app.functions.symbolic_from_latex import coalesce_step_symbolic
from app.functions.step_role import coalesce_step_role
from app.interfaces.crop_workspace import CropWorkspace
from app.interfaces.llm_client import LlmClient
from app.interfaces.recognizer import VisionRecognizer
from app.models.exam_schema import ExamSchema
from app.models.recognition import (
    DetectedRegion,
    PageRecognition,
    RecognizedQuestion,
    RecognizedStep,
    Region,
    SymbolicPayload,
)
from app.services.vision.ink_region_proposer import InkRegionProposer

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
CROP_MATH_PROMPT = _PROMPTS / "crop_math.txt"


def _prompt_version_from_file(path: Path, fallback: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^PROMPT_VERSION:\s*(\S+)", text, re.MULTILINE)
    return match.group(1) if match else fallback


PROMPT_VERSION = _prompt_version_from_file(CROP_MATH_PROMPT, "crop-math-v7")


def _coerce_step_number(value: object, fallback: int) -> int:
    """Accept an int step index; fall back when the model emits junk."""
    if not isinstance(value, (int, float, str)):
        return fallback
    try:
        number = int(value)
    except (OverflowError, ValueError):
        return fallback
    if number < 1:
        return fallback
    return number


class OllamaVisionRecognizer(VisionRecognizer, CropWorkspace):
    """Ink boxes → crop PNGs → optional crop_math symbolic JSON."""

    def __init__(
        self,
        client: LlmClient,
        model: str,
        output_dir: Path,
        crops_dir: Path | None = None,
        proposer: InkRegionProposer | None = None,
        prompt_version: str | None = None,
        expected_questions: list[tuple[int, str]] | None = None,
        exam_schema: ExamSchema | None = None,
    ) -> None:
        self._client = client
        self._model = model.strip()
        self._output_dir = Path(output_dir)
        self._crops_dir = Path(crops_dir) if crops_dir else self._output_dir.parent / "crops"
        self._prompt_version = prompt_version or PROMPT_VERSION
        self._math_prompt_template = CROP_MATH_PROMPT.read_text(encoding="utf-8")
        self._proposer = proposer or InkRegionProposer()
        self._exam_schema = exam_schema
        if exam_schema is not None and exam_schema.questions:
            self._expected_questions = [
                (q.number, q.stem) for q in exam_schema.questions if q.stem.strip()
            ]
            block = format_recognition_question_block(exam_schema)
        else:
            self._expected_questions = list(expected_questions or [])
            block = format_recognition_stems_block(self._expected_questions)
        self._expected_numbers = {n for n, _ in self._expected_questions}
        self._math_prompt = self._math_prompt_template.replace(
            "{{expected_questions}}",
            block,
        )

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def crops_dir(self) -> Path:
        return self._crops_dir

    def page_crop_dir(self, page_number: int) -> Path:
        return self._crops_dir / f"page_{page_number:03d}"

    def propose_page_crops(
        self, image_path: Path, page_number: int
    ) -> tuple[list[DetectedRegion], str, Path]:
        """Ink propose → write ``page_*_regions.json`` → Pillow crops (no VLM)."""
        image_path = Path(image_path)
        width, height = self._image_size(image_path)

        ink_detected = self._proposer.propose(image_path, page_number)
        ink_regions = self._merge_regions_by_question(ink_detected)

        if ink_regions:
            regions = ink_regions
            region_source = "ink"
        else:
            region_source = "fallback"
            regions = [
                DetectedRegion(
                    type="solution",
                    region=Region(x=0, y=0, width=width, height=height),
                    question_number=0,
                    order=0,
                )
            ]

        page_dir = self.page_crop_dir(page_number)
        json_path = write_regions_artifact(
            page_dir,
            page_number,
            regions=regions,
            source=region_source,
        )
        self._crop_regions_to_disk(image_path, page_dir, page_number, regions)
        logger.info(
            "proposed crops page=%s regions=%s source=%s json=%s",
            page_number,
            len(regions),
            region_source,
            json_path,
        )
        return regions, region_source, json_path

    def recrop_page_from_json(
        self, image_path: Path, page_number: int
    ) -> tuple[list[DetectedRegion], str, Path]:
        """Reload editable regions JSON and rewrite crop PNGs."""
        image_path = Path(image_path)
        page_dir = self.page_crop_dir(page_number)
        json_path = regions_json_path(page_dir, page_number)
        if not json_path.is_file():
            raise RegionsArtifactMissingError(json_path)
        _page, source, regions = load_regions_artifact(json_path)
        if not regions:
            raise EmptyRegionsError(json_path)
        # Refresh crop_path fields / keep source after edit
        write_regions_artifact(
            page_dir, page_number, regions=regions, source=source
        )
        self._crop_regions_to_disk(image_path, page_dir, page_number, regions)
        logger.info(
            "recropped page=%s regions=%s from %s",
            page_number,
            len(regions),
            json_path,
        )
        return regions, source, json_path

    def recognize_page(self, image_path: Path, page_number: int) -> PageRecognition:
        """Recognize from existing crops JSON+PNGs; propose first if missing."""
        if not self._model:
            raise OllamaModelNotConfiguredError()

        image_path = Path(image_path)
        page_dir = self.page_crop_dir(page_number)
        if not page_has_regions_artifact(page_dir, page_number):
            self.propose_page_crops(image_path, page_number)
        return self.recognize_page_from_crops(image_path, page_number)

    def recognize_page_from_crops(
        self, image_path: Path, page_number: int
    ) -> PageRecognition:
        """Run crop_math on PNGs listed in ``page_*_regions.json`` (no re-ink)."""
        if not self._model:
            raise OllamaModelNotConfiguredError()

        image_path = Path(image_path)
        # JSON boxes are the source of truth; refresh PNGs before the VLM.
        regions, region_source, _json_path = self.recrop_page_from_json(
            image_path, page_number
        )
        page_dir = self.page_crop_dir(page_number)

        questions: list[RecognizedQuestion] = []
        seen_numbers: set[int] = set()
        page_review = region_source == "fallback"
        question_map = self._load_question_map()

        for index, det in enumerate(regions):
            crop_path = page_dir / crop_filename(page_number, index)
            assigned = (question_map or {}).get(crop_path.name, [])

            for recognized in self._transcribe_math(
                crop_path=crop_path,
                page_number=page_number,
                detected=det,
                assigned_numbers=assigned,
            ):
                notes = [f"region_source={region_source}", recognized.reconcile_note]
                recognized = recognized.model_copy(
                    update={
                        "source": region_source,
                        "reconcile_note": "; ".join(n for n in notes if n),
                    }
                )

                qnum = recognized.question_number
                # User-assigned numbers may legitimately span several crops.
                if qnum > 0 and qnum in seen_numbers and qnum not in assigned:
                    logger.warning(
                        "page=%s duplicate question_number=%s from crop %s; "
                        "keeping with question_number=0 for audit",
                        page_number,
                        qnum,
                        crop_path.name,
                    )
                    recognized = recognized.model_copy(
                        update={
                            "question_number": 0,
                            "review_required": True,
                            "reconcile_note": (
                                f"{recognized.reconcile_note}; "
                                f"duplicate_of={qnum}"
                            ).strip("; "),
                        }
                    )
                    page_review = True
                elif qnum > 0:
                    seen_numbers.add(qnum)

                if recognized.review_required:
                    page_review = True
                questions.append(recognized)

        recognition = PageRecognition(
            page_number=page_number,
            questions=questions,
            prompt_version=self._prompt_version,
            model=self._model,
            region_source=region_source,
            review_required=page_review,
        )
        self._write_artifact(recognition)
        logger.info(
            "recognized page=%s solutions=%s model=%s source=%s",
            page_number,
            len(questions),
            self._model,
            region_source,
        )
        return recognition

    def _crop_regions_to_disk(
        self,
        image_path: Path,
        page_dir: Path,
        page_number: int,
        regions: list[DetectedRegion],
    ) -> list[Path]:
        paths: list[Path] = []
        keep: set[str] = set()
        for index, det in enumerate(regions):
            out = page_dir / crop_filename(page_number, index)
            result = crop_region(image_path, det.region, out)
            paths.append(result.path)
            keep.add(out.name)
        # Legacy ``region_*`` names predate the page prefix; drop them too.
        for pattern in ("page_*_region_*_solution.png", "region_*_solution.png"):
            for stale in page_dir.glob(pattern):
                if stale.name not in keep:
                    stale.unlink(missing_ok=True)
        return paths

    def _image_size(self, image_path: Path) -> tuple[int, int]:
        from PIL import Image

        with Image.open(image_path) as image:
            return image.size

    def _merge_regions_by_question(
        self, regions: list[DetectedRegion]
    ) -> list[DetectedRegion]:
        """Union boxes that share the same question_number; keep order."""
        if not regions:
            return []

        known: dict[int, list[DetectedRegion]] = defaultdict(list)
        unknown: list[DetectedRegion] = []
        for det in regions:
            if det.question_number > 0:
                known[det.question_number].append(det)
            else:
                unknown.append(det)

        merged: list[DetectedRegion] = []
        for qnum in sorted(known):
            group = known[qnum]
            boxes = [d.region for d in group]
            united = union_regions(boxes)
            if united is None:
                continue
            order = min(d.order for d in group)
            merged.append(
                DetectedRegion(
                    type="solution",
                    region=united,
                    question_number=qnum,
                    order=order,
                )
            )

        for det in unknown:
            merged.append(
                DetectedRegion(
                    type="solution",
                    region=det.region,
                    question_number=0,
                    order=det.order,
                )
            )

        return sorted(merged, key=lambda d: (d.order, d.question_number))

    def _resolve_question_number(
        self,
        llm_number: int,
        detected_number: int,
    ) -> int:
        """Prefer LLM number when it matches an expected stem; else ink fallback.

        Never accept an LLM number outside the exam schema (avoids phantom
        ``question_099`` dirs when ink could not label the crop).
        """
        if self._expected_numbers:
            if llm_number in self._expected_numbers:
                return llm_number
            if detected_number in self._expected_numbers:
                return detected_number
            return detected_number if detected_number > 0 else 0
        return llm_number or detected_number

    def _load_question_map(self) -> dict[str, list[int]] | None:
        """Crop name → user-confirmed question numbers; ``None`` if not labeled yet."""
        mapping = load_question_crops(self._crops_dir)
        return crop_to_questions(mapping) if mapping is not None else None

    def _prompt_for_crop(self, assigned_numbers: list[int]) -> str:
        if len(assigned_numbers) < 2:
            return self._math_prompt
        listed = ", ".join(str(n) for n in assigned_numbers)
        return (
            f"{self._math_prompt}\n\nThis crop contains exam questions {listed}. "
            'Return {"questions": [...]} with one object per question, and use only '
            f"these question_number values: {listed}."
        )

    def _transcribe_math(
        self,
        *,
        crop_path: Path,
        page_number: int,
        detected: DetectedRegion,
        assigned_numbers: list[int] | None = None,
    ) -> list[RecognizedQuestion]:
        assigned = list(assigned_numbers or [])
        prompt = self._prompt_for_crop(assigned)
        max_attempts = 3
        raw = ""
        for attempt in range(1, max_attempts + 1):
            raw = self._client.generate_with_image(prompt, crop_path, self._model)
            try:
                payload = extract_json_object(raw)
                break
            except ValueError as exc:
                logger.warning(
                    "page=%s crop_math JSON parse failed attempt=%s/%s: %s",
                    page_number,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt >= max_attempts:
                    self._write_raw_response(crop_path, raw, suffix="crop_math_failed")
                    raise InvalidRecognitionJsonError(page_number, str(exc)) from exc

        items = self._question_payloads(payload)
        return [
            self._recognized_from_payload(
                item,
                crop_path=crop_path,
                detected=detected,
                assigned_numbers=assigned,
            )
            for item in items
        ]

    def _write_raw_response(self, crop_path: Path, raw: str, *, suffix: str) -> Path:
        path = crop_path.with_name(f"{crop_path.stem}_{suffix}.txt")
        try:
            path.write_text(raw if raw else "(empty)", encoding="utf-8")
        except OSError as exc:
            logger.warning("could not write raw response %s: %s", path, exc)
        return path

    def _question_payloads(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        multi = payload.get("questions")
        if isinstance(multi, list) and multi:
            items = [item for item in multi if isinstance(item, dict)]
            if items:
                return items
        return [payload]

    def _recognized_from_payload(
        self,
        payload: dict[str, Any],
        *,
        crop_path: Path,
        detected: DetectedRegion,
        assigned_numbers: list[int] | None = None,
    ) -> RecognizedQuestion:
        assigned = list(assigned_numbers or [])
        llm_qnum = 0
        raw_qnum = payload.get("question_number")
        if raw_qnum is not None and raw_qnum != "":
            try:
                llm_qnum = int(raw_qnum)
            except (TypeError, ValueError):
                logger.warning(
                    "non-numeric question_number=%r in crop payload; using 0",
                    raw_qnum,
                )
                llm_qnum = 0
        review_required = False
        reconcile_note = ""
        if len(assigned) == 1:
            qnum = assigned[0]
        elif assigned:
            qnum = llm_qnum if llm_qnum in assigned else 0
            if qnum == 0:
                review_required = True
                reconcile_note = (
                    f"question_number={llm_qnum} not in assigned "
                    f"{','.join(str(n) for n in assigned)}"
                )
        else:
            qnum = self._resolve_question_number(llm_qnum, detected.question_number)
        steps_raw = payload.get("steps") or []
        steps: list[RecognizedStep] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            symbolic = item.get("symbolic")
            sym = None
            if isinstance(symbolic, dict):
                try:
                    sym = SymbolicPayload.model_validate(symbolic)
                except ValidationError:
                    sym = None
            raw_text = str(item.get("raw_text") or "")
            sym = coalesce_step_symbolic(raw_text, sym)
            role = coalesce_step_role(raw_text, sym, item.get("role"))
            steps.append(
                RecognizedStep(
                    step_number=_coerce_step_number(
                        item.get("step_number"), len(steps) + 1
                    ),
                    raw_text=raw_text,
                    latex="",
                    symbolic=sym,
                    role=role,
                    confidence=coerce_confidence(item.get("confidence")),
                )
            )

        final_answer = str(payload.get("final_answer") or "")
        final_sym = None
        if isinstance(payload.get("final_answer_symbolic"), dict):
            try:
                final_sym = SymbolicPayload.model_validate(
                    payload["final_answer_symbolic"]
                )
            except ValidationError:
                final_sym = None
        final_sym = coalesce_step_symbolic(final_answer, final_sym)

        return RecognizedQuestion(
            question_number=qnum,
            region=detected.region,
            region_type="solution",
            crop_path=str(crop_path),
            steps=steps,
            final_answer=final_answer,
            final_answer_symbolic=final_sym,
            latex_document=str(payload.get("latex_document") or ""),
            confidence=coerce_confidence(payload.get("confidence")),
            review_required=review_required,
            reconcile_note=reconcile_note,
        )

    def _write_artifact(self, recognition: PageRecognition) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / page_recognition_filename(recognition.page_number)
        path.write_text(
            recognition.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path
