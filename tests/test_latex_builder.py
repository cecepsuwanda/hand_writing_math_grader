from pathlib import Path

import pytest

from app.exceptions import QuestionsNotFoundError
from app.models.question import Question, StudentStep
from app.services.latex.builder import LatexBuilder


def test_builder_writes_student_tex_without_mutating_question_json(tmp_path: Path) -> None:
    question_dir = tmp_path / "question_001"
    question_dir.mkdir()
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(
                step_number=1,
                raw_text="keep_me_raw",
                latex="x < 4",
            )
        ],
        student_final_answer="x < 4",
    )
    question_path = question_dir / "question.json"
    original = question.model_dump_json(indent=2)
    question_path.write_text(original, encoding="utf-8")

    result = LatexBuilder().build_dir(tmp_path)

    tex_path = question_dir / "student.tex"
    assert tex_path.is_file()
    assert result.artifacts[0].path == tex_path
    assert "x &< 4" in tex_path.read_text(encoding="utf-8")
    assert question_path.read_text(encoding="utf-8") == original
    assert "keep_me_raw" in question_path.read_text(encoding="utf-8")


def test_builder_missing_questions(tmp_path: Path) -> None:
    with pytest.raises(QuestionsNotFoundError):
        LatexBuilder().build_dir(tmp_path)
