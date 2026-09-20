"""Thin segmenter wrapping deterministic question merge."""

from app.functions.question_merge import merge_page_recognitions
from app.models.question import Question
from app.models.recognition import PageRecognition


class QuestionSegmenter:
    def segment(self, pages: list[PageRecognition]) -> list[Question]:
        return merge_page_recognitions(pages)
