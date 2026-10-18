"""LLM scorer for pack-3 narrative / concept track (does not change other packs)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.exceptions import OllamaTimeoutError, OllamaUnavailableError
from app.functions.json_extract import coerce_confidence, extract_json_object
from app.functions.standard_extract import schema_question
from app.interfaces.llm_client import LlmClient
from app.models.exam_schema import ExamSchema
from app.models.question import Question
from app.models.validation import ValidationStatus

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / "concept_grade.txt"
)
PROMPT_VERSION = "concept-grade-v1"
CONCEPT_ROLE = "concept"
NO_REASONING_REASON = "no reasoning model for concept track"
HEURISTIC_REASON = "concept heuristic (LLM JSON invalid)"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|>=|<=|[≥≤≠∪∩∘]")
_STOP = frozenset(
    {
        "the",
        "and",
        "atau",
        "yang",
        "dari",
        "dengan",
        "untuk",
        "adalah",
        "karena",
        "sehingga",
        "maka",
        "jadi",
        "bahwa",
        "pada",
        "ini",
        "itu",
        "dan",
        "atau",
        "sebagai",
        "oleh",
        "harus",
        "bila",
        "jika",
        "when",
        "then",
        "that",
        "this",
        "with",
        "from",
        "into",
        "only",
        "also",
    }
)


class ConceptJudgement(BaseModel):
    status: ValidationStatus
    reason: str = ""
    fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ConceptComparer:
    """Compare student narrative steps to key ``concept`` milestones via LLM."""

    def __init__(
        self,
        client: LlmClient,
        model: str,
        exam_schema: ExamSchema | None,
        *,
        prompt_path: Path | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._client = client
        self._model = model.strip()
        self._schema = exam_schema
        self._prompt_path = Path(prompt_path) if prompt_path else DEFAULT_PROMPT_PATH
        self._prompt_version = prompt_version
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def compare(
        self, question: Question
    ) -> tuple[ValidationStatus, str, float | None]:
        """Return ``(status, reason, fraction)`` for the ``concept`` rubric part."""
        if not self._model:
            return ValidationStatus.UNCERTAIN, NO_REASONING_REASON, 0.0

        schema_q = schema_question(
            self._schema, question.question_number, question.part_label
        )
        key_concepts = _key_concept_text(schema_q)
        student_narrative = _student_narrative_text(question)
        if not key_concepts.strip() and not student_narrative.strip():
            return (
                ValidationStatus.UNCERTAIN,
                "no concept checklist or student narrative",
                None,
            )

        prompt = (
            self._template.replace("{{stem}}", (schema_q.stem if schema_q else "") or "(none)")
            .replace("{{key_concepts}}", key_concepts or "(none in key)")
            .replace(
                "{{student_narrative}}",
                student_narrative or "(no narrative steps)",
            )
        )
        try:
            raw = self._client.generate(prompt, self._model)
            payload = extract_json_object(raw)
            if isinstance(payload, dict) and "confidence" in payload:
                payload = {
                    **payload,
                    "confidence": coerce_confidence(payload["confidence"]),
                }
            judgement = ConceptJudgement.model_validate(payload)
        except (OllamaUnavailableError, OllamaTimeoutError) as exc:
            logger.warning("concept comparer unavailable: %s", exc)
            return _heuristic_concept_mark(
                key_concepts,
                student_narrative,
                reason_prefix=f"LLM unavailable: {exc}",
            )
        except (ValueError, ValidationError) as exc:
            logger.warning("concept comparer invalid response: %s", exc)
            return _heuristic_concept_mark(
                key_concepts,
                student_narrative,
                reason_prefix=f"{HEURISTIC_REASON}: {exc}",
            )

        reason = judgement.reason.strip() or "concept judgement"
        reason = f"{reason} (prompt={self._prompt_version})"
        return judgement.status, reason, judgement.fraction


def _heuristic_concept_mark(
    key_concepts: str,
    student_narrative: str,
    *,
    reason_prefix: str,
) -> tuple[ValidationStatus, str, float | None]:
    """Deterministic token overlap when the LLM JSON path fails."""
    key_tokens = _concept_tokens(key_concepts)
    student_tokens = _concept_tokens(student_narrative)
    if not key_tokens:
        if student_tokens:
            return (
                ValidationStatus.UNCERTAIN,
                f"{reason_prefix}; no key checklist",
                0.5,
            )
        return (
            ValidationStatus.UNCERTAIN,
            f"{reason_prefix}; empty concept texts",
            None,
        )
    if not student_tokens:
        return (
            ValidationStatus.INVALID,
            f"{reason_prefix}; no student narrative",
            0.0,
        )
    hits = len(key_tokens & student_tokens)
    fraction = hits / len(key_tokens)
    if fraction >= 0.85:
        status = ValidationStatus.VALID
    elif fraction <= 0.05:
        status = ValidationStatus.INVALID
    else:
        status = ValidationStatus.INVALID
    return status, f"{reason_prefix}; overlap {hits}/{len(key_tokens)}", fraction


def _concept_tokens(text: str) -> set[str]:
    tokens = {tok.lower() for tok in _TOKEN_RE.findall(text or "")}
    return {tok for tok in tokens if tok not in _STOP and len(tok) > 1}


def _key_concept_text(schema_q) -> str:
    if schema_q is None:
        return ""
    chunks: list[str] = []
    for milestone in schema_q.milestones:
        if milestone.role != CONCEPT_ROLE:
            continue
        if milestone.latex.strip():
            chunks.append(milestone.latex.strip())
        for step in milestone.steps:
            if step.strip():
                chunks.append(step.strip())
    return "\n".join(chunks)


def _student_narrative_text(question: Question) -> str:
    lines: list[str] = []
    for step in question.student_steps:
        is_concept = (step.role or "").strip().lower() == CONCEPT_ROLE
        has_math = bool(
            step.symbolic is not None
            and (step.symbolic.repr or "").strip()
            and step.symbolic.kind != "figure"
        )
        text = (step.raw_text or step.latex or "").strip()
        if is_concept or (text and not has_math and (step.role or "") != "figure"):
            if text:
                lines.append(f"{step.step_number}. {text}")
    for ref in question.figure_refs:
        caption = (ref.caption or "").strip()
        if caption and "NUMBER_LINE" not in caption.upper() and "GRAPH_POINTS" not in caption.upper():
            lines.append(f"figure: {caption}")
    return "\n".join(lines)
