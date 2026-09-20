from app.models.question import Question, StudentStep
from app.models.validation import ValidationStatus
from app.services.math.sympy_validator import SymPyStepValidator


def test_validator_known_valid_and_invalid_transforms() -> None:
    valid_q = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x+5=15"),
            StudentStep(step_number=2, raw_text="", latex="2x=10"),
            StudentStep(step_number=3, raw_text="", latex="x=5"),
        ],
        student_final_answer="x=5",
    )
    invalid_q = Question(
        question_id="question_002",
        question_number=2,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x+5=15"),
            StudentStep(step_number=2, raw_text="", latex="2x=20"),
        ],
    )

    validator = SymPyStepValidator()
    valid_result = validator.validate_question(valid_q)
    invalid_result = validator.validate_question(invalid_q)

    assert [s.status for s in valid_result.steps] == [
        ValidationStatus.VALID,
        ValidationStatus.VALID,
        ValidationStatus.VALID,
    ]
    assert valid_result.final_answer_status is not None
    assert valid_result.final_answer_status.status == ValidationStatus.VALID
    assert invalid_result.steps[1].status == ValidationStatus.INVALID


def test_validator_inequality_chain() -> None:
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x-3<5"),
            StudentStep(step_number=2, raw_text="", latex="2x<8"),
            StudentStep(step_number=3, raw_text="", latex="x<4"),
        ],
        student_final_answer="Jawaban akhir: x < 4",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_unparseable_is_uncertain() -> None:
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="lihat gambar", latex=""),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN
