"""Pure merge of per-page recognition into Question objects."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from app.functions.question_names import question_dir_name
from app.models.question import (
    FigureRef,
    ImageRegionRef,
    Question,
    SegmentationStatus,
    StudentStep,
)
from app.models.recognition import (
    PageRecognition,
    RecognizedQuestion,
    RecognizedStep,
    SymbolicPayload,
)


def merge_page_recognitions(
    pages: list[PageRecognition],
    reserved_numbers: Iterable[int] = (),
) -> list[Question]:
    """Merge page-scoped recognition into multi-page Question objects.

    Groups by question_number when valid (> 0). Fragments with invalid numbers
    become provisional questions with sequential numbers after both the read
    numbers and ``reserved_numbers`` (the answer-key numbers), so an unnumbered
    crop never takes the slot of a key question the student skipped.
    """
    sorted_pages = sorted(pages, key=lambda p: p.page_number)
    numbered: dict[int, list[tuple[int, RecognizedQuestion]]] = defaultdict(list)
    provisional: list[tuple[int, RecognizedQuestion]] = []

    for page in sorted_pages:
        for question in page.questions:
            if question.question_number > 0:
                numbered[question.question_number].append((page.page_number, question))
            else:
                provisional.append((page.page_number, question))

    questions: list[Question] = []
    for question_number in sorted(numbered):
        questions.append(
            _build_question(
                question_number=question_number,
                occurrences=numbered[question_number],
                status=SegmentationStatus.MERGED,
            )
        )

    next_provisional = _first_provisional_number(numbered.keys(), reserved_numbers)
    for page_number, fragment in provisional:
        questions.append(
            _build_question(
                question_number=next_provisional,
                occurrences=[(page_number, fragment)],
                status=SegmentationStatus.PROVISIONAL,
            )
        )
        next_provisional += 1

    return questions


def collect_latex_documents(
    pages: list[PageRecognition],
    reserved_numbers: Iterable[int] = (),
) -> dict[int, str]:
    """Map assigned question_number → latex (same numbering as ``merge_page_recognitions``).

    Unnumbered crops (``question_number=0``) become provisional keys
    ``max(known ∪ reserved)+1, …`` — one slot per fragment — so extract can find
    ``latex_source.tex`` after merge renumbers them.
    """
    sorted_pages = sorted(pages, key=lambda p: p.page_number)
    numbered: dict[int, list[str]] = defaultdict(list)
    provisional: list[str] = []
    known_numbers: set[int] = set()

    for page in sorted_pages:
        for question in page.questions:
            doc = (question.latex_document or "").strip()
            if question.question_number > 0:
                known_numbers.add(question.question_number)
                if doc:
                    numbered[question.question_number].append(doc)
            else:
                # Match merge: every qnum=0 fragment gets its own provisional number.
                provisional.append(doc)

    result = {
        qnum: "\n\n".join(parts) for qnum, parts in numbered.items() if parts
    }
    next_provisional = _first_provisional_number(known_numbers, reserved_numbers)
    for doc in provisional:
        if doc:
            result[next_provisional] = doc
        next_provisional += 1
    return result


def _first_provisional_number(
    read_numbers: Iterable[int], reserved_numbers: Iterable[int]
) -> int:
    return max({*read_numbers, *reserved_numbers}, default=0) + 1


def _build_question(
    question_number: int,
    occurrences: list[tuple[int, RecognizedQuestion]],
    status: SegmentationStatus,
) -> Question:
    occurrences = sorted(occurrences, key=lambda item: item[0])
    page_references = sorted({page_number for page_number, _ in occurrences})
    image_regions: list[ImageRegionRef] = []
    student_steps: list[StudentStep] = []
    figure_refs: list[FigureRef] = []
    confidences: list[float] = []
    final_answer = ""
    final_symbolic: SymbolicPayload | None = None

    for page_number, recognized in occurrences:
        image_regions.append(
            ImageRegionRef(
                page_number=page_number,
                region=recognized.region,
                region_type=recognized.region_type,
                crop_path=recognized.crop_path,
            )
        )
        if recognized.confidence is not None:
            confidences.append(recognized.confidence)

        if (
            recognized.region_type == "figure"
            and recognized.crop_path
            and _first_figure_step(recognized.steps) is None
        ):
            # No tagged figure step: keep the crop, without algebra symbolic.
            caption = recognized.steps[0].raw_text if recognized.steps else ""
            figure_refs.append(
                FigureRef(
                    path=recognized.crop_path,
                    caption=caption,
                    page_number=page_number,
                    symbolic=None,
                )
            )

        for step in sorted(recognized.steps, key=lambda s: s.step_number):
            if step.confidence is not None:
                confidences.append(step.confidence)
            # Figure steps inside a solution crop → figure_refs + skip math list.
            is_figure = _is_figure_step(step)
            if is_figure:
                figure_refs.append(
                    FigureRef(
                        path=recognized.crop_path or "",
                        caption=step.raw_text,
                        page_number=page_number,
                        symbolic=step.symbolic,
                    )
                )
                continue
            if recognized.region_type == "figure":
                continue
            student_steps.append(
                StudentStep(
                    step_number=0,
                    raw_text=step.raw_text,
                    latex="",
                    symbolic=step.symbolic,
                    role=step.role,
                    confidence=step.confidence,
                    page_number=page_number,
                )
            )
        # Text and symbolic must come from the same crop (a later crop wins as a pair).
        if recognized.final_answer.strip() or recognized.final_answer_symbolic is not None:
            final_answer = recognized.final_answer
            final_symbolic = recognized.final_answer_symbolic

    if not (final_answer or "").strip() and final_symbolic is not None:
        final_answer = (final_symbolic.repr or "").strip()

    if not (final_answer or "").strip():
        # Prefer the last HP step (earlier membership / uji-selang must not win).
        for student_step in reversed(student_steps):
            if student_step.role != "hp":
                continue
            symbolic = student_step.symbolic
            if symbolic is not None and (symbolic.repr or "").strip():
                final_answer = symbolic.repr.strip()
                final_symbolic = symbolic
                break
            if (student_step.raw_text or "").strip():
                final_answer = student_step.raw_text.strip()
                final_symbolic = None
                break

    for index, student_step in enumerate(student_steps, start=1):
        student_steps[index - 1] = student_step.model_copy(update={"step_number": index})

    confidence = min(confidences) if confidences else None
    return Question(
        question_id=question_dir_name(question_number),
        question_number=question_number,
        page_references=page_references,
        image_regions=image_regions,
        student_steps=student_steps,
        student_final_answer=final_answer,
        student_final_symbolic=final_symbolic,
        figure_refs=figure_refs,
        confidence=confidence,
        segmentation_status=status,
    )


def _is_figure_step(step: RecognizedStep) -> bool:
    return step.role == "figure" or (
        step.symbolic is not None and step.symbolic.kind == "figure"
    )


def _first_figure_step(steps: list[RecognizedStep]) -> RecognizedStep | None:
    for step in steps:
        if _is_figure_step(step):
            return step
    return None
