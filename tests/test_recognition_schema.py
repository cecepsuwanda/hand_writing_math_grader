import pytest
from pydantic import ValidationError

from app.models.recognition import PageRecognition


def test_page_recognition_valid_minimal() -> None:
    page = PageRecognition.model_validate(
        {
            "page_number": 1,
            "questions": [
                {
                    "question_number": 1,
                    "steps": [
                        {
                            "step_number": 1,
                            "raw_text": "x > 0",
                            "latex": "x > 0",
                        }
                    ],
                    "final_answer": "x > 0",
                }
            ],
        }
    )
    assert page.page_number == 1
    assert page.questions[0].steps[0].raw_text == "x > 0"


def test_page_recognition_with_confidence_and_region() -> None:
    page = PageRecognition.model_validate(
        {
            "page_number": 1,
            "questions": [
                {
                    "question_number": 1,
                    "region": {"x": 10, "y": 20, "width": 100, "height": 200},
                    "steps": [],
                    "final_answer": "",
                    "confidence": 0.8,
                }
            ],
            "prompt_version": "recognition-v1",
            "model": "test-model",
        }
    )
    assert page.questions[0].region is not None
    assert page.questions[0].region.x == 10
    assert page.questions[0].confidence == 0.8
    assert page.model == "test-model"


def test_page_recognition_rejects_bad_confidence() -> None:
    with pytest.raises(ValidationError):
        PageRecognition.model_validate(
            {
                "page_number": 1,
                "questions": [
                    {
                        "question_number": 1,
                        "steps": [],
                        "confidence": 1.5,
                    }
                ],
            }
        )
