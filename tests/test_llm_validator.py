import json
from pathlib import Path

import httpx

from app.models.question import Question, StudentStep
from app.models.validation import ValidationMethod, ValidationStatus
from app.services.math.hybrid_validator import HybridStepValidator
from app.services.math.llm_judge import LlmStepJudge
from app.services.math.sympy_validator import SymPyStepValidator
from app.services.vision.ollama_client import OllamaClient


class RecordingJudge:
    def __init__(self, response: dict | None = None, *, fail_json: bool = False) -> None:
        self.calls: list[tuple] = []
        self.response = response or {
            "status": "uncertain",
            "reason": "not enough evidence",
            "confidence": 0.4,
        }
        self.fail_json = fail_json

    def judge_transition(self, **kwargs):
        self.calls.append(("transition", kwargs))
        from app.models.validation import StepValidation

        if self.fail_json:
            return StepValidation(
                step_number=kwargs["step_number"],
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.LLM,
                reason="invalid LLM response: bad json",
            )
        return StepValidation(
            step_number=kwargs["step_number"],
            status=ValidationStatus(self.response["status"]),
            method=ValidationMethod.LLM,
            reason=self.response.get("reason", ""),
            confidence=self.response.get("confidence"),
        )

    def judge_final_answer(self, **kwargs):
        self.calls.append(("final", kwargs))
        return self.judge_transition(
            step_number=kwargs["step_number"],
            previous=kwargs.get("last_step"),
            current=None,
        )


def test_hybrid_preserves_llm_uncertain() -> None:
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="lihat gambar", latex=""),
        ],
    )
    judge = RecordingJudge(
        {"status": "uncertain", "reason": "unclear", "confidence": 0.3}
    )
    result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(  # type: ignore[arg-type]
        question
    )
    assert result.steps[0].status == ValidationStatus.UNCERTAIN
    assert result.steps[0].method == ValidationMethod.LLM
    assert judge.calls


def test_hybrid_llm_can_mark_valid_when_sympy_uncertain() -> None:
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="not parseable", latex=""),
        ],
    )
    judge = RecordingJudge(
        {"status": "valid", "reason": "looks ok", "confidence": 0.7}
    )
    result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(  # type: ignore[arg-type]
        question
    )
    assert result.steps[0].status == ValidationStatus.VALID
    assert result.steps[0].method == ValidationMethod.LLM


def test_hybrid_does_not_overwrite_sympy_invalid() -> None:
    question = Question(
        question_id="question_001",
        question_number=1,
        student_steps=[
            StudentStep(step_number=1, raw_text="", latex="2x+5=15"),
            StudentStep(step_number=2, raw_text="", latex="2x=20"),
        ],
    )
    judge = RecordingJudge(
        {"status": "valid", "reason": "should not be used", "confidence": 0.9}
    )
    result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(  # type: ignore[arg-type]
        question
    )
    assert result.steps[1].status == ValidationStatus.INVALID
    assert result.steps[1].method == ValidationMethod.SYMPY
    assert judge.calls == []


def test_llm_judge_invalid_json_stays_uncertain(tmp_path: Path) -> None:
    prompt = tmp_path / "validation.txt"
    prompt.write_text(
        "prev={{previous_step}}\ncur={{current_step}}\nextra={{extra_context}}",
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": "not-json"}},
        )

    client = OllamaClient(
        base_url="http://ollama.test",
        timeout_seconds=5,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    judge = LlmStepJudge(client=client, model="reason-test", prompt_path=prompt)
    step = StudentStep(step_number=2, raw_text="??", latex="")
    result = judge.judge_transition(
        step_number=2,
        previous=StudentStep(step_number=1, raw_text="a", latex="a"),
        current=step,
    )
    assert result.status == ValidationStatus.UNCERTAIN
    assert result.method == ValidationMethod.LLM


def test_ollama_generate_text_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert "images" not in body["messages"][0]
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": '{"status":"uncertain","reason":"r","confidence":0.5}'
                }
            },
        )

    client = OllamaClient(
        base_url="http://ollama.test",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    content = client.generate("prompt", "reason-test")
    assert "uncertain" in content
