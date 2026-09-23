"""LLM fallback judge for steps SymPy could not decide."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from app.exceptions import OllamaTimeoutError, OllamaUnavailableError
from app.functions.json_extract import extract_json_object, salvage_judgement_object
from app.models.question import StudentStep
from app.models.validation import (
    LlmJudgement,
    StepValidation,
    ValidationMethod,
    ValidationStatus,
)
from app.services.vision.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "validation.txt"
PROMPT_VERSION = "validation-v1"


class LlmStepJudge:
    def __init__(
        self,
        client: OllamaClient,
        model: str,
        prompt_path: Path | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._client = client
        self._model = model.strip()
        self._prompt_path = Path(prompt_path) if prompt_path else DEFAULT_PROMPT_PATH
        self._prompt_version = prompt_version
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def judge_transition(
        self,
        *,
        step_number: int,
        previous: StudentStep | None,
        current: StudentStep | None,
        extra_context: str = "",
    ) -> StepValidation:
        if not self._model:
            return StepValidation(
                step_number=step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.LLM,
                reason="reasoning model not configured",
            )

        prompt = self._render_prompt(
            previous=previous,
            current=current,
            extra_context=extra_context,
        )
        try:
            raw = self._client.generate(prompt, self._model)
            try:
                payload = extract_json_object(raw)
            except ValueError:
                salvaged = salvage_judgement_object(raw)
                if salvaged is None:
                    raise
                payload = salvaged
            judgement = LlmJudgement.model_validate(payload)
        except (OllamaUnavailableError, OllamaTimeoutError) as exc:
            logger.warning("LLM judge unavailable: %s", exc)
            return StepValidation(
                step_number=step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.LLM,
                reason=f"LLM unavailable: {exc}",
            )
        except (ValueError, ValidationError) as exc:
            logger.warning("LLM judge invalid JSON/schema: %s", exc)
            return StepValidation(
                step_number=step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.LLM,
                reason=f"invalid LLM response: {exc}",
            )

        reason = judgement.reason.strip() or "LLM judgement"
        reason = f"{reason} (prompt={self._prompt_version})"
        return StepValidation(
            step_number=step_number,
            status=judgement.status,
            method=ValidationMethod.LLM,
            reason=reason,
            confidence=judgement.confidence,
        )

    def judge_final_answer(
        self,
        *,
        step_number: int,
        last_step: StudentStep | None,
        final_answer: str,
    ) -> StepValidation:
        synthetic = StudentStep(
            step_number=step_number,
            raw_text=final_answer,
            latex=final_answer,
        )
        return self.judge_transition(
            step_number=step_number,
            previous=last_step,
            current=synthetic,
            extra_context="This current step is the student's declared final answer.",
        )

    def _render_prompt(
        self,
        *,
        previous: StudentStep | None,
        current: StudentStep | None,
        extra_context: str,
    ) -> str:
        return (
            self._template.replace("{{previous_step}}", self._format_step(previous))
            .replace("{{current_step}}", self._format_step(current))
            .replace("{{extra_context}}", extra_context.strip() or "(none)")
        )

    def _format_step(self, step: StudentStep | None) -> str:
        if step is None:
            return "(none)"
        raw = (step.raw_text or "").strip()
        symbolic = ""
        if step.symbolic is not None:
            symbolic = f"{step.symbolic.kind}:{step.symbolic.repr}"
        latex = (step.latex or "").strip()
        return (
            f"raw_text: {raw or '(empty)'}\n"
            f"symbolic: {symbolic or '(empty)'}\n"
            f"latex: {latex or '(empty)'}"
        )
