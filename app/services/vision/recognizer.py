"""Ink-only recognition: deterministic ink boxes → crop → crop_math symbolic JSON.

Region boxes: ink clustering (Pillow). Transcription: crop_math per crop.
Stem-only exam_schema context — never kunci steps/final.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.exceptions import (
    InvalidRecognitionJsonError,
    OllamaModelNotConfiguredError,
)
from app.functions.image_crop import crop_region, union_regions
from app.functions.json_extract import extract_json_object
from app.functions.kunci_ingest import (
    format_recognition_question_block,
    format_recognition_stems_block,
)
from app.functions.page_names import page_recognition_filename
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
from app.services.vision.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
CROP_MATH_PROMPT = _PROMPTS / "crop_math.txt"


def _prompt_version_from_file(path: Path, fallback: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^PROMPT_VERSION:\s*(\S+)", text, re.MULTILINE)
    return match.group(1) if match else fallback


PROMPT_VERSION = _prompt_version_from_file(CROP_MATH_PROMPT, "crop-math-v5")


def _coerce_step_number(value: object, fallback: int) -> int:
    """Accept an int step index; fall back when the model emits junk."""
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if number < 1:
        return fallback
    return number


def _coerce_confidence(value: object) -> float | None:
    """Keep confidence in ``[0, 1]``; drop values the schema would reject."""
    if value is None or value == "":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number < 0.0 or number > 1.0:
        return None
    return number


class OllamaVisionRecognizer(VisionRecognizer):
    """Ink boxes → crop → symbolic JSON via crop_math."""

    def __init__(
        self,
        client: OllamaClient,
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

    @property
    def expected_questions(self) -> list[tuple[int, str]]:
        return list(self._expected_questions)

    def recognize_page(self, image_path: Path, page_number: int) -> PageRecognition:
        if not self._model:
            raise OllamaModelNotConfiguredError()

        image_path = Path(image_path)
        width, height = self._image_size(image_path)

        ink_detected = self._proposer.propose(image_path, page_number)
        ink_regions = self._merge_regions_by_question(ink_detected)

        used_fallback = False
        if ink_regions:
            regions = ink_regions
            region_source = "ink"
        else:
            used_fallback = True
            region_source = "fallback"
            regions = [
                DetectedRegion(
                    type="solution",
                    region=Region(x=0, y=0, width=width, height=height),
                    question_number=0,
                    order=0,
                )
            ]

        page_crop_dir = self._crops_dir / f"page_{page_number:03d}"
        self._write_regions_artifact(
            page_crop_dir,
            page_number,
            regions=regions,
            ink=ink_regions,
            region_source=region_source,
        )

        questions: list[RecognizedQuestion] = []
        seen_numbers: set[int] = set()
        page_review = used_fallback

        for index, det in enumerate(regions):
            crop_name = f"region_{index:02d}_solution.png"
            crop_result = crop_region(
                image_path,
                det.region,
                page_crop_dir / crop_name,
            )
            crop_path = crop_result.path
            if crop_result.used_full_page_fallback:
                page_review = True

            for recognized in self._transcribe_math(
                crop_path=crop_path,
                page_number=page_number,
                detected=det,
            ):
                note_parts = [f"region_source={region_source}"]
                if crop_result.used_full_page_fallback:
                    note_parts.append("full_page_crop_fallback")
                recognized = recognized.model_copy(
                    update={
                        "source": region_source,
                        "reconcile_note": "; ".join(note_parts),
                    }
                )

                qnum = recognized.question_number
                if qnum > 0 and qnum in seen_numbers:
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

    def _image_size(self, image_path: Path) -> tuple[int, int]:
        from PIL import Image

        with Image.open(image_path) as image:
            return image.size

    @staticmethod
    def _region_dicts_with_crop_paths(
        regions: list[DetectedRegion],
    ) -> list[dict[str, Any]]:
        """Dump regions with relative crop_path (same files used by crop_math)."""
        return [
            {
                **r.model_dump(),
                "crop_path": f"region_{i:02d}_solution.png",
            }
            for i, r in enumerate(regions)
        ]

    def _write_regions_artifact(
        self,
        page_crop_dir: Path,
        page_number: int,
        *,
        regions: list[DetectedRegion],
        ink: list[DetectedRegion],
        region_source: str,
    ) -> Path:
        page_crop_dir.mkdir(parents=True, exist_ok=True)
        path = page_crop_dir / f"page_{page_number:03d}_regions.json"
        ink_payload = self._region_dicts_with_crop_paths(ink)
        payload = {
            "page_number": page_number,
            "source": region_source,
            "selected": [
                {
                    "source": region_source,
                    "detected": r.model_dump(),
                }
                for r in regions
            ],
            "ink": ink_payload,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if ink:
            ink_path = page_crop_dir / f"page_{page_number:03d}_regions_ink.json"
            ink_path.write_text(
                json.dumps(
                    {
                        "page_number": page_number,
                        "source": "ink_layout",
                        "regions": ink_payload,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return path

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
                    # ``order`` may be 0; treating it as missing sorted the
                    # first ink box after every later box.
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

    def _transcribe_math(
        self,
        *,
        crop_path: Path,
        page_number: int,
        detected: DetectedRegion,
    ) -> list[RecognizedQuestion]:
        # Cloud models often ignore format=json; retry a couple times before failing.
        max_attempts = 3
        last_error: Exception | None = None
        raw = ""
        for attempt in range(1, max_attempts + 1):
            raw = self._client.generate_with_image(
                self._math_prompt, crop_path, self._model
            )
            try:
                payload = extract_json_object(raw)
                break
            except ValueError as exc:
                last_error = exc
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
        else:
            self._write_raw_response(crop_path, raw, suffix="crop_math_failed")
            raise InvalidRecognitionJsonError(
                page_number, str(last_error or "unknown JSON parse failure")
            )

        items = self._question_payloads(payload)
        return [
            self._recognized_from_payload(
                item,
                crop_path=crop_path,
                detected=detected,
            )
            for item in items
        ]

    def _write_raw_response(self, crop_path: Path, raw: str, *, suffix: str) -> Path:
        """Persist failed model text next to the crop for audit/debug."""
        path = crop_path.with_name(f"{crop_path.stem}_{suffix}.txt")
        try:
            path.write_text(raw if raw else "(empty)", encoding="utf-8")
        except OSError as exc:
            logger.warning("could not write raw response %s: %s", path, exc)
        return path

    def _question_payloads(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return one or more per-question dicts from crop_math JSON."""
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
    ) -> RecognizedQuestion:
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
            steps.append(
                RecognizedStep(
                    step_number=_coerce_step_number(
                        item.get("step_number"), len(steps) + 1
                    ),
                    raw_text=str(item.get("raw_text") or ""),
                    latex="",
                    symbolic=sym,
                    confidence=_coerce_confidence(item.get("confidence")),
                )
            )

        final_sym = None
        if isinstance(payload.get("final_answer_symbolic"), dict):
            try:
                final_sym = SymbolicPayload.model_validate(
                    payload["final_answer_symbolic"]
                )
            except ValidationError:
                final_sym = None

        return RecognizedQuestion(
            question_number=qnum,
            region=detected.region,
            region_type="solution",
            crop_path=str(crop_path),
            steps=steps,
            final_answer=str(payload.get("final_answer") or ""),
            final_answer_symbolic=final_sym,
            latex_document=str(payload.get("latex_document") or ""),
            confidence=_coerce_confidence(payload.get("confidence")),
        )

    def _write_artifact(self, recognition: PageRecognition) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / page_recognition_filename(recognition.page_number)
        path.write_text(
            recognition.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path
