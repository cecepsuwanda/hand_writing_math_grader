"""Recognize question numbers per crop → editable question_crops JSON → confirm."""

from __future__ import annotations

from pathlib import Path

from app.exceptions import (
    NoRegionsForLabelingError,
    QuestionCropsInvalidError,
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
from app.models.exam_schema import ExamSchema
from app.models.question_crops import (
    LabelSource,
    QuestionCropMap,
    QuestionCropsReport,
    QuestionLabelResult,
)
from app.views.prompt_view import InputFn, is_interactive
from app.views.question_crops_view import (
    ask_question_crops_ok,
    print_question_crops_summary,
    wait_for_question_crops_edit,
)


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

    def label_all(self) -> QuestionLabelResult:
        """Detect labels per crop (vision), carry forward, write one JSON per question."""
        crops = list_crops_in_reading_order(self._crops_dir)
        if not crops:
            raise NoRegionsForLabelingError(self._crops_dir)

        labels: dict[str, list[int]] = {}
        if self._labeler is not None:
            for crop in crops:
                labels[crop.name] = self._labeler.detect(
                    crop_png_path(self._crops_dir, crop)
                )

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
        )
        return self._result(mapping, report, source)

    def reload_all(self) -> QuestionLabelResult:
        """Re-read edited question_*.json and validate against kunci + regions."""
        crops = list_crops_in_reading_order(self._crops_dir)
        mapping: QuestionCropMap = {}
        try:
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

    def confirm_loop(
        self,
        result: QuestionLabelResult,
        *,
        force_yes: bool = False,
        input_fn: InputFn | None = None,
    ) -> QuestionLabelResult:
        """Ask until mapping is OK and valid; on no, wait for JSON edit then reload."""
        if force_yes or not is_interactive(input_fn):
            if not result.report.ok:
                raise QuestionCropsInvalidError(result.report.errors)
            return result
        while True:
            if result.report.ok and ask_question_crops_ok(input_fn=input_fn):
                return result
            wait_for_question_crops_edit(json_dir=self.json_dir, input_fn=input_fn)
            result = self.reload_all()

    def _result(
        self,
        mapping: QuestionCropMap,
        report: QuestionCropsReport,
        source: LabelSource,
    ) -> QuestionLabelResult:
        print_question_crops_summary(mapping, report, json_dir=self.json_dir)
        return QuestionLabelResult(
            mapping=mapping, report=report, json_dir=self.json_dir, source=source
        )
