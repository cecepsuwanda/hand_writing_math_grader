from abc import ABC, abstractmethod

from app.models.question import Question
from app.models.validation import QuestionValidation


class StepValidator(ABC):
    @abstractmethod
    def validate_question(self, question: Question) -> QuestionValidation:
        """Validate student steps for one question."""
