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


def test_validator_abs_inequality_chain() -> None:
    question = Question(
        question_id="question_002",
        question_number=2,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex=r"|x-1|<3"),
            StudentStep(step_number=2, raw_text="", latex=r"-3<x-1<3"),
            StudentStep(step_number=3, raw_text="", latex=r"-2<x<4"),
        ],
        student_final_answer="-2 < x < 4",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_abs_wrong_transform_is_invalid() -> None:
    question = Question(
        question_id="question_002",
        question_number=2,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="|x|<2"),
            StudentStep(step_number=2, raw_text="", latex="x<2"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.VALID
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_abs_greater_than_or_chain() -> None:
    question = Question(
        question_id="question_002",
        question_number=2,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="|x|>2"),
            StudentStep(step_number=2, raw_text="", latex="x<-2 or x>2"),
        ],
        student_final_answer="x < -2 or x > 2",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_domain_inequality_chain() -> None:
    question = Question(
        question_id="question_003",
        question_number=3,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex=r"x \neq 1"),
            StudentStep(step_number=2, raw_text="", latex="x<1 or x>1"),
        ],
        student_final_answer=r"x \in (-\infty,1) \cup (1,\infty)",
    )
    # Final answer with infinity/union may be unparseable → only check steps
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_domain_interval_final() -> None:
    question = Question(
        question_id="question_003",
        question_number=3,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex=r"x \in (1,3)"),
            StudentStep(step_number=2, raw_text="", latex="1<x<3"),
        ],
        student_final_answer="1 < x < 3",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_function_operation_expressions() -> None:
    question = Question(
        question_id="question_003",
        question_number=3,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="(f+g)(x)=2x+1"),
            StudentStep(step_number=2, raw_text="", latex="y=2x+1"),
        ],
        student_final_answer="y=2x+1",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_wrong_expression_is_invalid() -> None:
    question = Question(
        question_id="question_003",
        question_number=3,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="(f+g)(x)=2x+1"),
            StudentStep(step_number=2, raw_text="", latex="y=2x+2"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_graph_prose_uncertain() -> None:
    question = Question(
        question_id="question_003",
        question_number=3,
        student_steps=[
            StudentStep(step_number=1, raw_text="grafik naik di kuadran I", latex=""),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_limit_cancel_chain() -> None:
    question = Question(
        question_id="question_004",
        question_number=4,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to 1} (x^2-1)/(x-1)",
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\lim_{x \to 1} (x+1)",
            ),
            StudentStep(step_number=3, raw_text="", latex="2"),
        ],
        student_final_answer="2",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_limit_wrong_value_invalid() -> None:
    question = Question(
        question_id="question_004",
        question_number=4,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to 1} (x^2-1)/(x-1)",
            ),
            StudentStep(step_number=2, raw_text="", latex="3"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_limit_infinity_finite_valid() -> None:
    question = Question(
        question_id="question_004",
        question_number=4,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to \infty} 1/x",
            ),
            StudentStep(step_number=2, raw_text="", latex="0"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.VALID
    assert result.steps[1].status == ValidationStatus.VALID


def test_validator_limit_infinity_divergent_uncertain() -> None:
    question = Question(
        question_id="question_004",
        question_number=4,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to \infty} x",
            ),
            StudentStep(step_number=2, raw_text="", latex="0"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.VALID
    assert result.steps[1].status == ValidationStatus.UNCERTAIN


def test_validator_limit_one_sided_finite() -> None:
    question = Question(
        question_id="question_004",
        question_number=4,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to 0^+} x",
            ),
            StudentStep(step_number=2, raw_text="", latex="0"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_continuity_chain_valid() -> None:
    question = Question(
        question_id="question_005",
        question_number=5,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to 1} (x^2-1)/(x-1)",
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\lim_{x \to 1} (x+1)",
            ),
            StudentStep(step_number=3, raw_text="", latex="2"),
            StudentStep(step_number=4, raw_text="", latex="f(1)=2"),
        ],
        student_final_answer="2",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_continuity_wrong_fa_invalid() -> None:
    question = Question(
        question_id="question_005",
        question_number=5,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\lim_{x \to 1} (x+1)",
            ),
            StudentStep(step_number=2, raw_text="", latex="f(1)=3"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_continuity_prose_uncertain() -> None:
    question = Question(
        question_id="question_005",
        question_number=5,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="f kontinu di a",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_derivative_chain_valid() -> None:
    question = Question(
        question_id="question_006",
        question_number=6,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\frac{d}{dx}(x^2+3x)",
            ),
            StudentStep(step_number=2, raw_text="", latex="2x+3"),
            StudentStep(step_number=3, raw_text="", latex="y'=2x+3"),
        ],
        student_final_answer="2x+3",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_derivative_wrong_invalid() -> None:
    question = Question(
        question_id="question_006",
        question_number=6,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\frac{d}{dx}(x^2+3x)",
            ),
            StudentStep(step_number=2, raw_text="", latex="2x"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_derivative_prose_uncertain() -> None:
    question = Question(
        question_id="question_006",
        question_number=6,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="turunan di a menurut definisi limit",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_integral_chain_valid() -> None:
    question = Question(
        question_id="question_007",
        question_number=7,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\int (2x+3)\,dx",
            ),
            StudentStep(step_number=2, raw_text="", latex="x^2+3x+C"),
        ],
        student_final_answer="x^2+3x+C",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_integral_wrong_invalid() -> None:
    question = Question(
        question_id="question_007",
        question_number=7,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\int (2x+3)\,dx",
            ),
            StudentStep(step_number=2, raw_text="", latex="x^2"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_integral_prose_uncertain() -> None:
    question = Question(
        question_id="question_007",
        question_number=7,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="anti turunan dengan substitusi u",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_transcendental_ln_chain_valid() -> None:
    question = Question(
        question_id="question_008",
        question_number=8,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\frac{d}{dx}(\ln x)",
            ),
            StudentStep(step_number=2, raw_text="", latex=r"1/x"),
        ],
        student_final_answer=r"1/x",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_transcendental_exp_chain_valid() -> None:
    question = Question(
        question_id="question_008",
        question_number=8,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\frac{d}{dx}(e^{2x})",
            ),
            StudentStep(step_number=2, raw_text="", latex=r"2e^{2x}"),
        ],
        student_final_answer=r"2e^{2x}",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_transcendental_integral_valid() -> None:
    question = Question(
        question_id="question_008",
        question_number=8,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\int e^x\,dx",
            ),
            StudentStep(step_number=2, raw_text="", latex=r"e^x+C"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_transcendental_wrong_invalid() -> None:
    question = Question(
        question_id="question_008",
        question_number=8,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\frac{d}{dx}(\ln x)",
            ),
            StudentStep(step_number=2, raw_text="", latex=r"1/x^2"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_transcendental_prose_uncertain() -> None:
    question = Question(
        question_id="question_008",
        question_number=8,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="sifat ln: ln(ab)=ln a + ln b",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_matrix_add_chain_valid() -> None:
    question = Question(
        question_id="question_009",
        question_number=9,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=(
                    r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}"
                    r"+\begin{pmatrix}5 & 6 \\ 7 & 8\end{pmatrix}"
                ),
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\begin{pmatrix}6 & 8 \\ 10 & 12\end{pmatrix}",
            ),
        ],
        student_final_answer=r"\begin{pmatrix}6 & 8 \\ 10 & 12\end{pmatrix}",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_matrix_transpose_valid() -> None:
    question = Question(
        question_id="question_009",
        question_number=9,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}^{T}",
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 3 \\ 2 & 4\end{pmatrix}",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_matrix_wrong_invalid() -> None:
    question = Question(
        question_id="question_009",
        question_number=9,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=(
                    r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}"
                    r"+\begin{pmatrix}5 & 6 \\ 7 & 8\end{pmatrix}"
                ),
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 1 \\ 1 & 1\end{pmatrix}",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_matrix_prose_uncertain() -> None:
    question = Question(
        question_id="question_009",
        question_number=9,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="matriks A berukuran 2x2 simetris",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_det_chain_valid() -> None:
    question = Question(
        question_id="question_010",
        question_number=10,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\det\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}",
            ),
            StudentStep(step_number=2, raw_text="", latex="-2"),
        ],
        student_final_answer="-2",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_det_wrong_invalid() -> None:
    question = Question(
        question_id="question_010",
        question_number=10,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\det\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}",
            ),
            StudentStep(step_number=2, raw_text="", latex="2"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_inverse_chain_valid() -> None:
    question = Question(
        question_id="question_010",
        question_number=10,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}^{-1}",
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\begin{pmatrix}-2 & 1 \\ 3/2 & -1/2\end{pmatrix}",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_inverse_wrong_invalid() -> None:
    question = Question(
        question_id="question_010",
        question_number=10,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}^{-1}",
            ),
            StudentStep(
                step_number=2,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 0 \\ 0 & 1\end{pmatrix}",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_singular_inverse_uncertain() -> None:
    question = Question(
        question_id="question_010",
        question_number=10,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=r"\begin{pmatrix}1 & 0 \\ 0 & 0\end{pmatrix}^{-1}",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_det_prose_uncertain() -> None:
    question = Question(
        question_id="question_010",
        question_number=10,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="A invertible karena det tidak nol",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN


def test_validator_vector_norm_chain_valid() -> None:
    question = Question(
        question_id="question_011",
        question_number=11,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex=r"||<3,4>||"),
            StudentStep(step_number=2, raw_text="", latex="5"),
        ],
        student_final_answer="5",
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)
    assert result.final_answer_status is not None
    assert result.final_answer_status.status == ValidationStatus.VALID


def test_validator_vector_norm_wrong_invalid() -> None:
    question = Question(
        question_id="question_011",
        question_number=11,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex=r"||<3,4>||"),
            StudentStep(step_number=2, raw_text="", latex="6"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_vector_dot_chain_valid() -> None:
    question = Question(
        question_id="question_011",
        question_number=11,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=(
                    r"\begin{pmatrix}1 \\ 2\end{pmatrix}"
                    r"\cdot\begin{pmatrix}3 \\ 4\end{pmatrix}"
                ),
            ),
            StudentStep(step_number=2, raw_text="", latex="11"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert all(s.status == ValidationStatus.VALID for s in result.steps)


def test_validator_vector_dot_wrong_invalid() -> None:
    question = Question(
        question_id="question_011",
        question_number=11,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="",
                latex=(
                    r"\begin{pmatrix}1 \\ 2\end{pmatrix}"
                    r"\cdot\begin{pmatrix}3 \\ 4\end{pmatrix}"
                ),
            ),
            StudentStep(step_number=2, raw_text="", latex="0"),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[1].status == ValidationStatus.INVALID


def test_validator_vector_angle_prose_uncertain() -> None:
    question = Question(
        question_id="question_011",
        question_number=11,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="sudut antara u dan v adalah arccos",
                latex="",
            ),
        ],
    )
    result = SymPyStepValidator().validate_question(question)
    assert result.steps[0].status == ValidationStatus.UNCERTAIN
