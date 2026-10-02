"""Terminal progress and process summary presentation."""

from __future__ import annotations

from app.models.process import ProcessProgress, ProcessResult
from app.models.report import MISSING_UNANSWERED
from app.views.result_view import print_report_paths
from app.views.style import banner, bar, bold, box, cyan, dim, green, rule


def print_models(*, vision_model: str, reasoning_model: str) -> None:
    print(banner())
    print()
    lines = [
        bold("Model (config.yaml)"),
        f"Vision:    {vision_model.strip() or '(unset)'}",
        f"Reasoning: {reasoning_model.strip() or '(unset)'}",
    ]
    print(cyan(box(lines)))
    print()
    print(bold("Progress"))
    print(rule())


def print_progress(progress: ProcessProgress) -> None:
    overall = progress.completed / progress.total if progress.total else 0.0
    stage = progress.stage.value
    print(
        f"  {green('✓')} {stage:<20} {bar(1.0)} 100%  "
        f"(overall {bar(overall)} {int(round(overall * 100)):3d}%)"
    )


def print_process_summary(result: ProcessResult) -> None:
    print()
    print(rule("Results"))
    rows: list[str] = []
    for q in result.questions:
        status = (
            f"{q.missing_label or MISSING_UNANSWERED}, {q.review_status.value}"
            if q.missing
            else q.review_status.value
        )
        rows.append(
            f"Q{q.question_number:<3}  {q.score:g}/{q.maximum_score:g}  {status}"
        )
    rows.append(rule(width=36))
    total_line = (
        f"Total  {result.total_score:g}/{result.maximum_total:g}  "
        f"{result.overall_status.value}"
    )
    rows.append(bold(total_line))
    print(box(rows))
    print()
    print(bold("Artifacts"))
    print(dim(f"  dir:  {result.output_dir}"))
    print_report_paths(result)
    print()
