from app.functions.latex_transforms import (
    build_student_latex,
    escape_latex_text,
    format_aligned_line,
    normalize_step_latex,
    strip_final_answer_prefix,
)
from app.models.question import Question, StudentStep


def test_escape_latex_text() -> None:
    assert escape_latex_text("a_b & 50%") == r"a\_b \& 50\%"


def test_normalize_prefers_latex() -> None:
    step = StudentStep(step_number=1, raw_text="raw", latex="x < 4")
    assert normalize_step_latex(step) == "x < 4"


def test_normalize_falls_back_to_escaped_raw() -> None:
    step = StudentStep(step_number=1, raw_text="a_b\nc", latex="")
    assert normalize_step_latex(step) == r"a\_b c"


def test_format_aligned_line_with_inequality() -> None:
    assert format_aligned_line("2x - 3 < 5") == "2x - 3 &< 5"
    assert format_aligned_line("2x = 10") == "2x &= 10"


def test_strip_final_answer_prefix() -> None:
    assert strip_final_answer_prefix("Jawaban akhir: x < 4") == "x < 4"
    assert strip_final_answer_prefix("final answer - y=1") == "y=1"


def test_build_student_latex_aligned() -> None:
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="...", latex="2x - 3 < 5"),
            StudentStep(step_number=2, raw_text="...", latex="2x < 8"),
            StudentStep(step_number=3, raw_text="...", latex="x < 4"),
        ],
        student_final_answer="Jawaban akhir: x < 4",
    )
    tex = build_student_latex(question)
    assert r"\begin{aligned}" in tex
    assert r"\end{aligned}" in tex
    assert "2x - 3 &< 5" in tex
    assert "2x &< 8" in tex
    assert "x &< 4" in tex
    assert "% final answer" in tex
    assert "x < 4" in tex
    assert "Jawaban akhir" not in tex.split("% final answer", 1)[1]
