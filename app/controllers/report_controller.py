"""Orchestrate exam report generation from grading.json artifacts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import GradingNotFoundError, ReportWriteError
from app.functions.question_names import (
    grading_filename,
    report_html_filename,
    report_json_filename,
    summary_csv_filename,
)
from app.functions.report_aggregate import aggregate_exam_report
from app.interfaces.reporter import GradeReporter
from app.models.grading import QuestionGrade
from app.models.report import PromptVersions, ReportMetadata, ReportResult
from app.services.grading.feedback_annotator import PROMPT_VERSION as GRADING_PROMPT
from app.services.math.llm_judge import PROMPT_VERSION as VALIDATION_PROMPT
from app.services.vision.recognizer import PROMPT_VERSION as RECOGNITION_PROMPT

logger = logging.getLogger(__name__)


class ReportController:
    def __init__(
        self,
        reporter: GradeReporter,
        *,
        standard_dir: Path,
        vision_model: str = "",
        reasoning_model: str = "",
    ) -> None:
        self._reporter = reporter
        self._standard_dir = Path(standard_dir)
        self._vision_model = vision_model
        self._reasoning_model = reasoning_model

    def report(
        self,
        questions_dir: Path,
        output_dir: Path,
        *,
        student_id: str = "student_001",
    ) -> ReportResult:
        questions_dir = Path(questions_dir)
        output_dir = Path(output_dir)
        paths = sorted(questions_dir.glob(f"*/{grading_filename()}"))
        if not paths:
            raise GradingNotFoundError(questions_dir)

        grades: list[QuestionGrade] = []
        for path in paths:
            try:
                grades.append(
                    QuestionGrade.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValidationError, ValueError) as exc:
                raise ReportWriteError(f"invalid grading artifact {path}: {exc}") from exc

        # Snapshot source bytes to detect mutation after write
        source_snapshots = {p: p.read_bytes() for p in paths}

        metadata = ReportMetadata(
            generated_at=datetime.now(timezone.utc).isoformat(),
            standard_dir=self._standard_dir,
            questions_dir=questions_dir,
            student_id=student_id,
            vision_model=self._vision_model,
            reasoning_model=self._reasoning_model,
            prompt_versions=PromptVersions(
                recognition=RECOGNITION_PROMPT,
                validation=VALIDATION_PROMPT,
                grading=GRADING_PROMPT,
            ),
        )
        exam = aggregate_exam_report(grades, metadata)
        written = self._reporter.write(exam, output_dir)

        for path, original in source_snapshots.items():
            if path.read_bytes() != original:
                raise ReportWriteError(
                    f"grading artifact was modified during report: {path}"
                )

        by_name = {p.name: p for p in written}
        result = ReportResult(
            exam_report=exam,
            output_dir=output_dir,
            report_json_path=by_name.get(
                report_json_filename(), output_dir / report_json_filename()
            ),
            summary_csv_path=by_name.get(
                summary_csv_filename(), output_dir / summary_csv_filename()
            ),
            report_html_path=by_name.get(
                report_html_filename(), output_dir / report_html_filename()
            ),
        )
        logger.info(
            "Reported %s question(s) for %s -> %s",
            len(grades),
            student_id,
            output_dir,
        )
        return result
