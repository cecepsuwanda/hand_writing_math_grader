"""Read the run-level ``report.json`` written by the report stage."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from app.functions.question_names import report_json_filename
from app.models.report import ExamReport


def load_exam_report(run_root: Path) -> ExamReport | None:
    """``report.json`` of a run; ``None`` before the first report.

    Raises:
        ValueError: the file exists but cannot be parsed.
    """
    path = Path(run_root) / report_json_filename()
    if not path.is_file():
        return None
    try:
        return ExamReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ValueError(f"invalid report artifact {path}: {exc}") from exc
