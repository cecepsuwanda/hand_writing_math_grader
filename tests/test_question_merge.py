from app.functions.question_merge import merge_page_recognitions
from app.functions.question_names import question_dir_name
from app.models.question import SegmentationStatus
from app.models.recognition import (
    PageRecognition,
    RecognizedQuestion,
    RecognizedStep,
    Region,
)


def test_question_dir_name() -> None:
    assert question_dir_name(1) == "question_001"
    assert question_dir_name(12) == "question_012"


def test_merge_single_page() -> None:
    pages = [
        PageRecognition(
            page_number=1,
            questions=[
                RecognizedQuestion(
                    question_number=1,
                    region=Region(x=1, y=2, width=3, height=4),
                    steps=[
                        RecognizedStep(
                            step_number=1,
                            raw_text="2x-3<5",
                            latex="2x-3<5",
                            confidence=0.9,
                        ),
                        RecognizedStep(
                            step_number=2,
                            raw_text="x<4",
                            latex="x<4",
                            confidence=0.8,
                        ),
                    ],
                    final_answer="x<4",
                    confidence=0.85,
                )
            ],
        )
    ]

    questions = merge_page_recognitions(pages)

    assert len(questions) == 1
    q = questions[0]
    assert q.question_id == "question_001"
    assert q.question_number == 1
    assert q.page_references == [1]
    assert len(q.student_steps) == 2
    assert q.student_steps[0].step_number == 1
    assert q.student_steps[1].raw_text == "x<4"
    assert q.student_final_answer == "x<4"
    assert q.segmentation_status == SegmentationStatus.MERGED
    assert q.confidence == 0.8


def test_merge_multi_page_same_question_number() -> None:
    pages = [
        PageRecognition(
            page_number=1,
            questions=[
                RecognizedQuestion(
                    question_number=1,
                    steps=[
                        RecognizedStep(step_number=1, raw_text="start", latex=""),
                    ],
                    final_answer="",
                )
            ],
        ),
        PageRecognition(
            page_number=2,
            questions=[
                RecognizedQuestion(
                    question_number=1,
                    steps=[
                        RecognizedStep(step_number=1, raw_text="end", latex=""),
                    ],
                    final_answer="x < 4",
                )
            ],
        ),
    ]

    questions = merge_page_recognitions(pages)

    assert len(questions) == 1
    q = questions[0]
    assert q.page_references == [1, 2]
    assert [s.raw_text for s in q.student_steps] == ["start", "end"]
    assert [s.step_number for s in q.student_steps] == [1, 2]
    assert [s.page_number for s in q.student_steps] == [1, 2]
    assert q.student_final_answer == "x < 4"
    assert len(q.image_regions) == 2


def test_merge_two_distinct_questions() -> None:
    pages = [
        PageRecognition(
            page_number=1,
            questions=[
                RecognizedQuestion(
                    question_number=2,
                    steps=[RecognizedStep(step_number=1, raw_text="q2", latex="")],
                    final_answer="a2",
                ),
                RecognizedQuestion(
                    question_number=1,
                    steps=[RecognizedStep(step_number=1, raw_text="q1", latex="")],
                    final_answer="a1",
                ),
            ],
        )
    ]

    questions = merge_page_recognitions(pages)

    assert [q.question_id for q in questions] == ["question_001", "question_002"]
    assert questions[0].student_final_answer == "a1"
    assert questions[1].student_final_answer == "a2"


def test_merge_provisional_invalid_number() -> None:
    pages = [
        PageRecognition(
            page_number=1,
            questions=[
                RecognizedQuestion(
                    question_number=0,
                    steps=[RecognizedStep(step_number=1, raw_text="frag", latex="")],
                    final_answer="?",
                )
            ],
        )
    ]

    questions = merge_page_recognitions(pages)

    assert len(questions) == 1
    assert questions[0].question_number == 1
    assert questions[0].question_id == "question_001"
    assert questions[0].segmentation_status == SegmentationStatus.PROVISIONAL
