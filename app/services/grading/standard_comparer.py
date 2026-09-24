"""Compare student final answer to standard solution via SymPy equivalence."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sympy import Expr, Symbol
from sympy.logic.boolalg import Boolean

from app.exceptions import MathParseError
from app.functions.kunci_ingest import load_exam_schema
from app.functions.standard_extract import (
    schema_question,
    standard_final_text,
    standard_method_step_banks,
    standard_solution_path,
    standard_step_texts,
)
from app.functions.step_align import align_student_steps_to_standard
from app.models.exam_schema import ExamMilestone, ExamSchema
from app.models.question import Question, StudentStep
from app.models.validation import ValidationStatus
from app.services.math.equivalence import (
    derivatives_equivalent,
    expressions_equivalent,
    integrals_equivalent,
    limits_equivalent,
    matrices_equivalent,
    relations_equivalent,
    relations_form_equivalent,
    set_relation_equivalent,
    try_set_form_equivalence,
)
from app.services.math.parser import (
    DerivativeClaim,
    IntegralClaim,
    LimitClaim,
    MatrixClaim,
    ParsedStep,
    default_symbol,
    parse_math_step,
)

logger = logging.getLogger(__name__)

# Split joined critical-point lists (``;`` or ``\;``). Do not split logical "and".
_ATOM_SPLIT_RE = re.compile(r"\s*\\?;\s*")


def _mark_fraction(
    mark: tuple[ValidationStatus, str, float | None],
) -> float:
    status, _reason, fraction = mark
    if fraction is not None:
        return fraction
    if status == ValidationStatus.VALID:
        return 1.0
    if status == ValidationStatus.UNCERTAIN:
        return 0.5
    return 0.0


def _average_marks(
    left: tuple[ValidationStatus, str, float | None],
    right: tuple[ValidationStatus, str, float | None],
) -> tuple[ValidationStatus, str, float | None]:
    """Mean of two milestone marks. Both roles count toward one rubric bucket."""
    mean = (_mark_fraction(left) + _mark_fraction(right)) / 2
    undecided = (
        left[0] == ValidationStatus.UNCERTAIN
        or right[0] == ValidationStatus.UNCERTAIN
    )
    reason = f"{left[1]}; {right[1]}"
    if mean >= 1.0 - 1e-9:
        return ValidationStatus.VALID, reason, 1.0
    if undecided and left[2] is None and right[2] is None and mean <= 0.5 + 1e-9:
        return ValidationStatus.UNCERTAIN, reason, None
    if mean <= 1e-9:
        return ValidationStatus.INVALID, reason, 0.0
    if undecided:
        return ValidationStatus.UNCERTAIN, reason, mean
    return ValidationStatus.INVALID, reason, mean


def _milestone_atom_texts(milestone: ExamMilestone) -> list[str]:
    """Positional milestone claims. Prefer step lists over a joined blob."""
    raw: list[str] = []
    step_reprs = [
        (step.repr or "").strip()
        for step in milestone.steps_symbolic or []
        if step is not None and (step.repr or "").strip()
    ]
    step_tex = [(step or "").strip() for step in milestone.steps or [] if (step or "").strip()]
    if step_reprs:
        raw.extend(step_reprs)
    elif step_tex:
        raw.extend(step_tex)
    elif milestone.symbolic is not None and (milestone.symbolic.repr or "").strip():
        raw.append(milestone.symbolic.repr.strip())
    elif (milestone.latex or "").strip():
        raw.append(milestone.latex.strip())

    atoms: list[str] = []
    for text in raw:
        for piece in _ATOM_SPLIT_RE.split(text):
            cleaned = piece.strip()
            if cleaned:
                atoms.append(cleaned)
    return atoms


@dataclass(frozen=True)
class _RowBuild:
    kind: str  # "row" | "skip" | "early"
    row: list[bool | None] | None = None
    reason: str | None = None
    status_reason: tuple[ValidationStatus, str] | None = None


class StandardFinalComparer:
    """Compare student answers to exam_schema symbolic (fallback solutions/*.tex)."""

    def __init__(
        self,
        standard_dir: Path,
        exam_schema: ExamSchema | None = None,
        symbol: Symbol | None = None,
    ) -> None:
        self._standard_dir = Path(standard_dir)
        self._schema = (
            exam_schema
            if exam_schema is not None
            else load_exam_schema(self._standard_dir)
        )
        self._symbol = symbol or default_symbol()

    def compare(
        self,
        question: Question,
    ) -> tuple[ValidationStatus, str] | None:
        """Return (status, reason), or None if no schema question and no .tex."""
        schema_q = schema_question(self._schema, question.question_number)
        path = standard_solution_path(
            self._standard_dir, question.question_number
        )
        tex: str | None = None
        if path.is_file():
            try:
                tex = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read standard solution %s: %s", path, exc)
                if schema_q is None:
                    return (
                        ValidationStatus.UNCERTAIN,
                        f"could not read standard solution: {path}",
                    )

        if schema_q is None and tex is None:
            return None

        standard_text = standard_final_text(schema_q, tex)
        if not standard_text:
            return (
                ValidationStatus.UNCERTAIN,
                "no standard final answer in schema or TeX",
            )

        student_text = self._student_final_text(question)
        if not student_text:
            return ValidationStatus.INVALID, "student final answer is empty"

        try:
            student_step = parse_math_step(student_text, self._symbol)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse student final answer for standard compare",
            )

        try:
            standard_step = parse_math_step(standard_text, self._symbol)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse standard final answer",
            )

        result = self._equivalent(student_step, standard_step)
        if result is True:
            return ValidationStatus.VALID, "final answer matches standard"
        if result is False:
            return ValidationStatus.INVALID, "final answer differs from standard"
        return (
            ValidationStatus.UNCERTAIN,
            "SymPy could not decide final vs standard equivalence",
        )

    def compare_steps(
        self,
        question: Question,
    ) -> dict[int, tuple[ValidationStatus, str]] | None:
        """Best-method monotonic soft-align of student steps to standard banks.

        When the schema has alternate ``methods``, each bank is
        ``shared + method``; the bank with the most VALID (then fewest
        INVALID) wins. Align is audit/feedback; scoring uses consistency.
        """
        schema_q = schema_question(self._schema, question.question_number)
        path = standard_solution_path(
            self._standard_dir, question.question_number
        )
        tex: str | None = None
        if path.is_file():
            try:
                tex = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read standard solution %s: %s", path, exc)
                if schema_q is None:
                    steps = sorted(
                        question.student_steps, key=lambda s: s.step_number
                    )
                    return {
                        step.step_number: (
                            ValidationStatus.UNCERTAIN,
                            f"could not read standard solution: {path}",
                        )
                        for step in steps
                    }

        if schema_q is None and tex is None:
            return None

        banks = standard_method_step_banks(schema_q, tex)
        if not banks:
            # Legacy TeX-only fallback. Empty means nothing to align:
            # callers must not invent per-step INVALID audits.
            texts = standard_step_texts(schema_q, tex)
            if not any(text.strip() for text in texts):
                return None
            banks = [("shared", texts)]

        student_steps = sorted(question.student_steps, key=lambda s: s.step_number)
        best: dict[int, tuple[ValidationStatus, str]] | None = None
        best_key: tuple[int, int] | None = None  # (valid, -invalid)

        for bank_id, standard_texts in banks:
            aligned = self._align_to_texts(
                student_steps, standard_texts, bank_id=bank_id
            )
            valid = sum(
                1 for _, (st, _) in aligned.items() if st == ValidationStatus.VALID
            )
            invalid = sum(
                1
                for _, (st, _) in aligned.items()
                if st == ValidationStatus.INVALID
            )
            key = (valid, -invalid)
            if best_key is None or key > best_key:
                best_key = key
                best = aligned

        return best if best is not None else {}

    def compare_milestones(
        self,
        question: Question,
    ) -> dict[str, tuple[ValidationStatus, str]]:
        """Coverage of student work vs schema milestones.

        Returns keys used by part scoring. When both ``critical_points``
        and ``sign_chart`` exist, their score fractions are averaged into
        the single ``critical_points`` rubric bucket.
        """
        schema_q = schema_question(self._schema, question.question_number)
        if schema_q is None or not schema_q.milestones:
            return {}

        role_results: dict[str, tuple[ValidationStatus, str, float | None]] = {}
        for milestone in schema_q.milestones:
            if milestone.role == "hp":
                continue
            mark = self._milestone_match(question, milestone)
            prev = role_results.get(milestone.role)
            if prev is None or _mark_fraction(mark) > _mark_fraction(prev):
                role_results[milestone.role] = mark

        out: dict[str, tuple[ValidationStatus, str, float | None]] = {}
        cp = role_results.get("critical_points")
        sc = role_results.get("sign_chart")
        if cp is not None and sc is not None:
            # Rubric folds both roles into one bucket; both must contribute.
            out["critical_points"] = _average_marks(cp, sc)
        elif cp is not None:
            out["critical_points"] = cp
        elif sc is not None:
            out["critical_points"] = sc
        return out

    def _milestone_match(
        self,
        question: Question,
        milestone: ExamMilestone,
    ) -> tuple[ValidationStatus, str, float | None]:
        """Coverage of milestone atoms, not a single matching fragment.

        The third value is an explicit score fraction when coverage is
        partial. ``None`` means the caller should use ``score_fraction``.
        """
        texts = _milestone_atom_texts(milestone)
        if not texts:
            return (
                ValidationStatus.UNCERTAIN,
                f"empty milestone {milestone.role}",
                None,
            )

        standard_parsed: list[ParsedStep] = []
        unparsed = 0
        for text in texts:
            try:
                standard_parsed.append(parse_math_step(text, self._symbol))
            except MathParseError:
                unparsed += 1
        if not standard_parsed and unparsed:
            return (
                ValidationStatus.UNCERTAIN,
                f"could not parse milestone {milestone.role}",
                None,
            )
        if not standard_parsed:
            return (
                ValidationStatus.UNCERTAIN,
                f"empty milestone {milestone.role}",
                None,
            )

        students: list[ParsedStep] = []
        for step in question.student_steps:
            if step.role == "figure" or (
                step.symbolic is not None and step.symbolic.kind == "figure"
            ):
                continue
            student_text = ""
            if step.symbolic is not None and (step.symbolic.repr or "").strip():
                student_text = step.symbolic.repr.strip()
            if not student_text:
                student_text = (
                    (step.latex or "").strip() or (step.raw_text or "").strip()
                )
            if not student_text:
                continue
            try:
                students.append(parse_math_step(student_text, self._symbol))
            except MathParseError:
                continue

        matched = 0
        saw_false = 0
        saw_undecided = unparsed
        for atom in standard_parsed:
            outcome: bool | None = None
            for student in students:
                eq = self._equivalent(student, atom)
                if eq is True:
                    outcome = True
                    break
                if eq is False:
                    outcome = False
            if outcome is True:
                matched += 1
            elif outcome is False:
                saw_false += 1
            else:
                saw_undecided += 1

        total = matched + saw_false + saw_undecided
        if total <= 0:
            return (
                ValidationStatus.UNCERTAIN,
                f"empty milestone {milestone.role}",
                None,
            )
        fraction = matched / total
        if matched == total:
            return (
                ValidationStatus.VALID,
                f"matches milestone {milestone.role}",
                1.0,
            )
        if matched == 0 and saw_false == 0:
            return (
                ValidationStatus.UNCERTAIN,
                f"could not decide milestone {milestone.role}",
                None,
            )
        if matched == 0:
            return (
                ValidationStatus.INVALID,
                f"no student step matches milestone {milestone.role}",
                0.0,
            )
        return (
            ValidationStatus.INVALID,
            f"matches {matched}/{total} of milestone {milestone.role}",
            fraction,
        )

    def _align_to_texts(
        self,
        student_steps: list[StudentStep],
        standard_texts: list[str],
        *,
        bank_id: str,
    ) -> dict[int, tuple[ValidationStatus, str]]:
        standard_parsed: list[ParsedStep | None] = []
        for text in standard_texts:
            try:
                standard_parsed.append(parse_math_step(text, self._symbol))
            except MathParseError:
                standard_parsed.append(None)

        rows: list[tuple[int, list[bool | None] | None]] = []
        skip_reasons: dict[int, str] = {}
        early: dict[int, tuple[ValidationStatus, str]] = {}

        for step in student_steps:
            built = self._student_equivalence_row(step, standard_parsed)
            if built.kind == "early":
                assert built.status_reason is not None
                early[step.step_number] = built.status_reason
                continue
            if built.kind == "skip":
                rows.append((step.step_number, None))
                skip_reasons[step.step_number] = built.reason or (
                    "figure step skipped for standard align"
                )
                continue
            rows.append((step.step_number, built.row or []))

        aligned = align_student_steps_to_standard(
            rows, skip_reasons=skip_reasons
        )
        aligned.update(early)
        # Annotate reasons with bank id for audit transparency.
        annotated: dict[int, tuple[ValidationStatus, str]] = {}
        for step_number, (status, reason) in aligned.items():
            if bank_id and bank_id != "shared":
                annotated[step_number] = (
                    status,
                    f"{reason} (method: {bank_id})",
                )
            else:
                annotated[step_number] = (status, reason)
        return annotated

    def _student_equivalence_row(
        self,
        step: StudentStep,
        standard_parsed: list[ParsedStep | None],
    ) -> _RowBuild:
        if step.role == "figure" or (
            step.symbolic is not None and step.symbolic.kind == "figure"
        ):
            return _RowBuild(
                kind="skip",
                reason="figure step skipped for standard align",
            )
        student_text = ""
        if step.symbolic is not None and (step.symbolic.repr or "").strip():
            student_text = step.symbolic.repr.strip()
        if not student_text:
            student_text = (step.latex or "").strip() or (step.raw_text or "").strip()
        if not student_text:
            return _RowBuild(
                kind="early",
                status_reason=(
                    ValidationStatus.INVALID,
                    "student step is empty",
                ),
            )

        try:
            student_parsed = parse_math_step(student_text, self._symbol)
        except MathParseError:
            return _RowBuild(
                kind="skip",
                reason="could not parse student step for standard align",
            )

        row: list[bool | None] = []
        for std in standard_parsed:
            if std is None:
                row.append(None)
                continue
            row.append(self._align_equivalent(student_parsed, std))
        return _RowBuild(kind="row", row=row)

    def _student_final_text(self, question: Question) -> str:
        if (
            question.student_final_symbolic is not None
            and (question.student_final_symbolic.repr or "").strip()
        ):
            return question.student_final_symbolic.repr.strip()
        final = (question.student_final_answer or "").strip()
        if final:
            return final
        for step in sorted(question.student_steps, key=lambda s: s.step_number):
            if step.role != "hp":
                continue
            if step.symbolic is not None and (step.symbolic.repr or "").strip():
                return step.symbolic.repr.strip()
            text = (step.latex or "").strip() or (step.raw_text or "").strip()
            if text:
                return text
        if not question.student_steps:
            return ""
        last = max(question.student_steps, key=lambda s: s.step_number)
        if last.symbolic is not None and (last.symbolic.repr or "").strip():
            return last.symbolic.repr.strip()
        latex = (last.latex or "").strip()
        if latex:
            return latex
        return (last.raw_text or "").strip()

    def _align_equivalent(
        self,
        student: ParsedStep,
        standard: ParsedStep,
    ) -> bool | None:
        """Stricter match for soft-align: relational *form*, not solution set."""
        if student.kind == "relation" and standard.kind == "relation":
            assert isinstance(student.value, Boolean)
            assert isinstance(standard.value, Boolean)
            return relations_form_equivalent(student.value, standard.value)
        return self._equivalent(student, standard)

    def _equivalent(
        self,
        student: ParsedStep,
        standard: ParsedStep,
    ) -> bool | None:
        if student.kind == "relation" and standard.kind == "relation":
            assert isinstance(student.value, Boolean)
            assert isinstance(standard.value, Boolean)
            return relations_equivalent(
                student.value, standard.value, self._symbol
            )

        applicable, set_result = try_set_form_equivalence(
            student.kind,
            student.value,
            standard.kind,
            standard.value,
            self._symbol,
        )
        if applicable:
            return set_result

        if student.kind == "expression" and standard.kind == "expression":
            assert isinstance(student.value, Expr)
            assert isinstance(standard.value, Expr)
            return expressions_equivalent(student.value, standard.value)

        # Interval / set expression ↔ relation (HP forms).
        if student.kind == "expression" and standard.kind == "relation":
            assert isinstance(standard.value, Boolean)
            return set_relation_equivalent(
                student.value, standard.value, self._symbol
            )
        if student.kind == "relation" and standard.kind == "expression":
            assert isinstance(student.value, Boolean)
            return set_relation_equivalent(
                standard.value, student.value, self._symbol
            )

        if student.kind == "limit" or standard.kind == "limit":
            return self._limit_pair(student, standard)

        if student.kind == "derivative" or standard.kind == "derivative":
            return self._derivative_pair(student, standard)

        if student.kind == "integral" or standard.kind == "integral":
            return self._integral_pair(student, standard)

        if student.kind == "matrix" and standard.kind == "matrix":
            assert isinstance(student.value, MatrixClaim)
            assert isinstance(standard.value, MatrixClaim)
            return matrices_equivalent(student.value, standard.value)

        return None

    def _limit_pair(
        self, student: ParsedStep, standard: ParsedStep
    ) -> bool | None:
        if student.kind == "limit" and standard.kind == "limit":
            assert isinstance(student.value, LimitClaim)
            assert isinstance(standard.value, LimitClaim)
            return limits_equivalent(student.value, standard.value)
        if student.kind == "limit" and standard.kind == "expression":
            assert isinstance(student.value, LimitClaim)
            assert isinstance(standard.value, Expr)
            return limits_equivalent(student.value, standard.value)
        if standard.kind == "limit" and student.kind == "expression":
            assert isinstance(standard.value, LimitClaim)
            assert isinstance(student.value, Expr)
            return limits_equivalent(standard.value, student.value)
        return None

    def _derivative_pair(
        self, student: ParsedStep, standard: ParsedStep
    ) -> bool | None:
        if student.kind == "derivative" and standard.kind == "derivative":
            assert isinstance(student.value, DerivativeClaim)
            assert isinstance(standard.value, DerivativeClaim)
            return derivatives_equivalent(student.value, standard.value)
        if student.kind == "derivative" and standard.kind == "expression":
            assert isinstance(student.value, DerivativeClaim)
            assert isinstance(standard.value, Expr)
            return derivatives_equivalent(student.value, standard.value)
        if standard.kind == "derivative" and student.kind == "expression":
            assert isinstance(standard.value, DerivativeClaim)
            assert isinstance(student.value, Expr)
            return derivatives_equivalent(standard.value, student.value)
        return None

    def _integral_pair(
        self, student: ParsedStep, standard: ParsedStep
    ) -> bool | None:
        if student.kind == "integral" and standard.kind == "integral":
            assert isinstance(student.value, IntegralClaim)
            assert isinstance(standard.value, IntegralClaim)
            return integrals_equivalent(student.value, standard.value)
        if student.kind == "integral" and standard.kind == "expression":
            assert isinstance(student.value, IntegralClaim)
            assert isinstance(standard.value, Expr)
            return integrals_equivalent(student.value, standard.value)
        if standard.kind == "integral" and student.kind == "expression":
            assert isinstance(standard.value, IntegralClaim)
            assert isinstance(student.value, Expr)
            return integrals_equivalent(standard.value, student.value)
        return None
