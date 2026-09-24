"""Pure merge of per-page recognition into Question objects."""

from __future__ import annotations

from collections import defaultdict

from app.functions.question_names import question_dir_name
from app.models.question import (
    FigureRef,
    ImageRegionRef,
    Question,
    SegmentationStatus,
    StudentStep,
)
from app.models.recognition import PageRecognition, RecognizedQuestion, SymbolicPayload


def merge_page_recognitions(pages: list[PageRecognition]) -> list[Question]:
    """Merge page-scoped recognition into multi-page Question objects.

    Groups by question_number when valid (> 0). Fragments with invalid numbers
    become provisional questions with sequential numbers after known ones.
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

    next_provisional = (max(numbered.keys()) if numbered else 0) + 1
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


def collect_latex_documents(pages: list[PageRecognition]) -> dict[int, str]:
    """Map assigned question_number → latex (same numbering as ``merge_page_recognitions``).

    Unnumbered crops (``question_number=0``) become provisional keys
    ``max(known)+1, …`` — one slot per fragment — so extract can find
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
    next_provisional = (max(known_numbers) if known_numbers else 0) + 1
    for doc in provisional:
        if doc:
            result[next_provisional] = doc
        next_provisional += 1
    return result


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

        if recognized.region_type == "figure" and recognized.crop_path:
            caption = ""
            if recognized.steps:
                caption = recognized.steps[0].raw_text
            figure_refs.append(
                FigureRef(
                    path=recognized.crop_path,
                    caption=caption,
                    page_number=page_number,
                )
            )

        for step in sorted(recognized.steps, key=lambda s: s.step_number):
            if step.confidence is not None:
                confidences.append(step.confidence)
            # Figure steps inside a solution crop → figure_refs + skip math list.
            is_figure = step.role == "figure" or (
                step.symbolic is not None and step.symbolic.kind == "figure"
            )
            if is_figure:
                if recognized.crop_path:
                    figure_refs.append(
                        FigureRef(
                            path=recognized.crop_path,
                            caption=step.raw_text,
                            page_number=page_number,
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
        if recognized.final_answer.strip():
            final_answer = recognized.final_answer
        if recognized.final_answer_symbolic is not None:
            final_symbolic = recognized.final_answer_symbolic

    if not (final_answer or "").strip():
        for step in student_steps:
            if step.role != "hp":
                continue
            if step.symbolic is not None and (step.symbolic.repr or "").strip():
                final_answer = step.symbolic.repr.strip()
                final_symbolic = step.symbolic
                break
            if (step.raw_text or "").strip():
                final_answer = step.raw_text.strip()
                break

    for index, step in enumerate(student_steps, start=1):
        student_steps[index - 1] = step.model_copy(update={"step_number": index})

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
