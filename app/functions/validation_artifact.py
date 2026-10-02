"""Read ``question.json`` and write ``validation.json`` per question folder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.functions.question_names import question_artifact_filename, validation_filename
from app.models.question import Question
from app.models.validation import QuestionValidation


def question_fingerprint(question: Question) -> str:
    """sha256 of the graded student work (steps + final answer)."""
    payload = question.model_dump(
        mode="json",
        include={"student_steps", "student_final_answer", "student_final_symbolic"},
    )
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def question_artifact_paths(questions_dir: Path) -> list[Path]:
    return sorted(Path(questions_dir).glob(f"*/{question_artifact_filename()}"))


def load_question_artifact(path: Path) -> Question:
    """Parse one question.json; ``ValueError`` if unreadable or invalid."""
    try:
        return Question.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


def write_validation_artifact(question_dir: Path, validation: QuestionValidation) -> Path:
    """Write validation.json next to question.json; ``OSError`` propagates."""
    path = Path(question_dir) / validation_filename()
    path.write_text(validation.model_dump_json(indent=2), encoding="utf-8")
    return path
