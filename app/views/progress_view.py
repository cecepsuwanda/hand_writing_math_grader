"""Terminal progress and process summary presentation."""

from __future__ import annotations

from app.models.process import ProcessProgress, ProcessResult


def print_models(*, vision_model: str, reasoning_model: str) -> None:
    print("[ Select models from app/config/config.yaml ]")
    print(f"Vision model:    {vision_model.strip() or '(unset)'}")
    print(f"Reasoning model: {reasoning_model.strip() or '(unset)'}")
    print()
    print("Progress:")


def _bar(fraction: float, width: int = 10) -> str:
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    return "█" * filled + "░" * (width - filled)


def print_progress(progress: ProcessProgress) -> None:
    overall = progress.completed / progress.total if progress.total else 0.0
    print(
        f"  {progress.stage.value:<20} {_bar(1.0)} 100%  "
        f"(overall {_bar(overall)} {int(round(overall * 100)):3d}%)"
    )


def print_process_summary(result: ProcessResult) -> None:
    print()
    print("Results")
    print("-----------------------------------------")
    for q in result.questions:
        print(
            f"Question {q.question_number:<3} "
            f"{q.score:g}/{q.maximum_score:g}  {q.review_status.value}"
        )
    print("-----------------------------------------")
    print(
        f"Total         {result.total_score:g}/{result.maximum_total:g}  "
        f"{result.overall_status.value}"
    )
    print()
    print(f"Artifacts written to: {result.output_dir}")
    if result.report_json_path:
        print(f"  JSON: {result.report_json_path}")
    if result.summary_csv_path:
        print(f"  CSV:  {result.summary_csv_path}")
    if result.report_html_path:
        print(f"  HTML: {result.report_html_path}")
