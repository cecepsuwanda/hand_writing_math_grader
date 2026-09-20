"""Pure merge of per-page recognition into Question objects."""

from __future__ import annotations

from collections import defaultdict

from app.functions.question_names import question_dir_name
from app.models.question import (
    ImageRegionRef,
    Question,
    SegmentationStatus,
    StudentStep,
)
from app.models.recognition import PageRecognition, RecognizedQuestion


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


def _build_question(
    question_number: int,
    occurrences: list[tuple[int, RecognizedQuestion]],
    status: SegmentationStatus,
) -> Question:
    occurrences = sorted(occurrences, key=lambda item: item[0])
    page_references = sorted({page_number for page_number, _ in occurrences})
    image_regions: list[ImageRegionRef] = []
    student_steps: list[StudentStep] = []
    confidences: list[float] = []
    final_answer = ""

    for page_number, recognized in occurrences:
        image_regions.append(
            ImageRegionRef(page_number=page_number, region=recognized.region)
        )
        if recognized.confidence is not None:
            confidences.append(recognized.confidence)
        for step in sorted(recognized.steps, key=lambda s: s.step_number):
            if step.confidence is not None:
                confidences.append(step.confidence)
            student_steps.append(
                StudentStep(
                    step_number=0,  # renumber below
                    raw_text=step.raw_text,
                    latex=step.latex,
                    confidence=step.confidence,
                    page_number=page_number,
                )
            )
        if recognized.final_answer.strip():
            final_answer = recognized.final_answer

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
        confidence=confidence,
        segmentation_status=status,
    )
