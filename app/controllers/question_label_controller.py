"""Recognize question numbers per crop → editable question_crops JSON."""

from __future__ import annotations

import logging
from pathlib import Path

from app.exceptions import (
    NoRegionsForLabelingError,
    QuestionCropsNotFoundError,
)
from app.functions.question_crops import (
    assign_by_labels,
    assign_sequential,
    crop_png_path,
    list_crops_in_reading_order,
    load_question_crops,
    question_crops_dir,
    validate_question_crops,
    write_question_crops,
)
from app.interfaces.question_labeler import QuestionLabeler
from app.models.exam_schema import ExamQuestion, ExamSchema
from app.models.question_crops import (
    LabelSource,
    QuestionCropMap,
    QuestionCropsReport,
    QuestionLabelResult,
)

logger = logging.getLogger(__name__)


class QuestionLabelController:
    def __init__(
        self,
        *,
        crops_dir: Path,
        exam_schema: ExamSchema,
        labeler: QuestionLabeler | None = None,
    ) -> None:
        self._crops_dir = Path(crops_dir)
        self._schema = exam_schema
        self._labeler = labeler

    @property
    def json_dir(self) -> Path:
        return question_crops_dir(self._crops_dir)

    @property
    def _numbers(self) -> list[int]:
        return sorted(q.number for q in self._schema.questions)

    @property
    def exam_questions(self) -> list[ExamQuestion]:
        return sorted(self._schema.questions, key=lambda q: q.number)

    def save_mapping(self, mapping: QuestionCropMap) -> QuestionLabelResult:
        """Write a mapping edited in the UI, then validate it exactly like a reload."""
        stems = {q.number: q.stem for q in self._schema.questions}
        write_question_crops(self._crops_dir, mapping, stems=stems)
        return self.reload_all()

    def label_all(self) -> QuestionLabelResult:
        """Detect labels per crop (vision), carry forward, write one JSON per question."""
        crops = list_crops_in_reading_order(self._crops_dir)
        if not crops:
            raise NoRegionsForLabelingError(self._crops_dir)

        labels: dict[str, list[int]] = {}
        unreadable: list[str] = []
        if self._labeler is not None:
            for crop in crops:
                detected = self._labeler.detect(crop_png_path(self._crops_dir, crop))
                if detected is None:
                    unreadable.append(crop.name)
                labels[crop.name] = detected or []

        if any(labels.values()):
            mapping = assign_by_labels(crops, labels, self._numbers)
            source = LabelSource.VISION
        else:
            mapping = assign_sequential(crops, self._numbers)
            source = LabelSource.SEQUENTIAL

        stems = {q.number: q.stem for q in self._schema.questions}
        write_question_crops(self._crops_dir, mapping, stems=stems)
        report = validate_question_crops(
            mapping, self._numbers, [c.name for c in crops]
        ).model_copy(update={"unreadable_crops": unreadable})
        return self._result(mapping, report, source)

    def reload_all(self) -> QuestionLabelResult:
        """Re-read edited question_*.json and validate against kunci + regions."""
        mapping: QuestionCropMap = {}
        try:
            crops = list_crops_in_reading_order(self._crops_dir)
            loaded = load_question_crops(self._crops_dir)
        except ValueError as exc:
            report = QuestionCropsReport(errors=[str(exc)])
        else:
            if loaded is None:
                report = QuestionCropsReport(
                    errors=[str(QuestionCropsNotFoundError(self.json_dir))]
                )
            else:
                mapping = loaded
                report = validate_question_crops(
                    mapping, self._numbers, [c.name for c in crops]
                )
        return self._result(mapping, report, LabelSource.RELOAD)

    def _result(
        self,
        mapping: QuestionCropMap,
        report: QuestionCropsReport,
        source: LabelSource,
    ) -> QuestionLabelResult:
        logger.info(
            "question crops (%s): %d question(s), %d error(s), %d unassigned, %d unreadable in %s",
            source.value,
            len(mapping),
            len(report.errors),
            len(report.unassigned_crops),
            len(report.unreadable_crops),
            self.json_dir,
        )
        return QuestionLabelResult(
            mapping=mapping, report=report, json_dir=self.json_dir, source=source
        )
