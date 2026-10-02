"""CLI view for reviewing transcribed question.json before validation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.models.question_review import QuestionReviewItem, QuestionReviewResult
from app.views.error_view import print_warning
from app.views.prompt_view import InputFn, ask_yes_no, wait_for_edit
from app.views.style import bold, dim, yellow


def _print_item(item: QuestionReviewItem) -> None:
    question = item.question
    flags_by_step = {f.step_number: f.flags for f in item.flagged_steps}
    print(bold(f"Soal {question.question_number}") + dim(f"  ({item.path})"))
    for step in sorted(question.student_steps, key=lambda s: s.step_number):
        repr_text = (step.symbolic.repr if step.symbolic is not None else "") or "-"
        role = step.role or "-"
        line = f"  {step.step_number:>2}. [{role}] {step.raw_text}"
        print(line)
        print(dim(f"      symbolic: {repr_text}"))
        flags = flags_by_step.get(step.step_number)
        if flags:
            print(yellow(f"      periksa: {', '.join(f.value for f in flags)}"))
    final = (
        question.student_final_symbolic.repr
        if question.student_final_symbolic is not None
        else ""
    ) or question.student_final_answer or "-"
    print(f"  Jawaban akhir: {final}")
    print()


def print_question_review_summary(result: QuestionReviewResult) -> None:
    flagged = sum(len(item.flagged_steps) for item in result.items)
    print(bold(f"Transkripsi per soal ({len(result.items)} soal, {flagged} langkah ditandai)"))
    print()
    for item in result.items:
        _print_item(item)
    for error in result.errors:
        print_warning(f"  Error: {error}")
    print(dim(f"  Folder: {result.questions_dir}"))
    print()


def ask_transcription_ok(*, input_fn: InputFn | None = None) -> bool:
    """Return True if user accepts the transcription. Empty / y / yes → True."""
    return ask_yes_no("Transkripsi OK? [y/n]: ", input_fn=input_fn)


def wait_for_question_edit(*, questions_dir: Path, input_fn: InputFn | None = None) -> bool:
    """False when input ended (EOF) instead of Enter."""
    return wait_for_edit(
        "Edit question_*/question.json (SymPy membaca \"symbolic.repr\"; "
        "\"raw_text\" hanya untuk tampilan/laporan),"
        f"\nsimpan, lalu tekan Enter untuk memuat ulang.\n  {questions_dir}",
        input_fn=input_fn,
    )


def print_question_edits(edited_ids: Sequence[str]) -> None:
    print(dim(f"Soal diedit: {', '.join(edited_ids)} (latex_source.tex lama dihapus)"))
    print()
