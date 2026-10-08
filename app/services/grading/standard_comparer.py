"""Compare student final answer to standard solution via SymPy equivalence."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sympy import Expr, FiniteSet, Symbol
from sympy.logic.boolalg import Boolean

from app.exceptions import MathParseError
from app.functions.kunci_ingest import load_exam_schema
from app.functions.math_normalize import split_implication_clauses
from app.functions.number_line import (
    compare_number_lines,
    number_line_from_symbolic,
    parse_number_line_intervals_only,
)
from app.functions.standard_extract import (
    schema_question,
    standard_final_text,
    standard_method_step_banks,
    standard_solution_path,
    standard_step_texts,
)
from app.functions.question_split import schema_final_text, schema_stem_text
from app.functions.sign_chart import caption_signs, evaluation_row_signs, format_signs
from app.functions.step_align import align_student_steps_to_standard
from app.models.exam_schema import ExamMilestone, ExamQuestion, ExamSchema, NumberLineSpec
from app.models.question import FigureRef, Question, StudentStep
from app.models.validation import ValidationStatus
from app.services.math.equivalence import (
    derivatives_equivalent,
    expressions_equivalent,
    integrals_equivalent,
    is_solved_form,
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
    infer_main_symbol,
    parse_math_step,
    rebind_default_symbol,
)
from app.services.math.role_checks import finite_solutions

logger = logging.getLogger(__name__)

FIGURE_UNCOMPARED_REASON = "figure present; no key number line to compare"
SIGN_CHART_ROLE = "sign_chart"
HP_ROLE = "hp"
HP_ALIGN_SKIP_REASON = "HP step is compared as the final answer"
SIGN_CHART_IN_FIGURE_REASON = "sign chart only in figure; needs review"

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
        self._fixed_symbol = symbol
        self._symbol = symbol or default_symbol()

    def _bind_symbol(self, question: Question) -> ExamQuestion | None:
        """Pick the question's variable (stem, key final, student work); return its schema entry."""
        schema_q = schema_question(self._schema, question.question_number)
        if self._fixed_symbol is not None:
            self._symbol = self._fixed_symbol
            return schema_q
        texts: list[str] = []
        if schema_q is not None:
            texts.extend([schema_stem_text(schema_q), schema_final_text(schema_q)])
        texts.extend(_student_step_text(step) for step in question.student_steps)
        texts.append(question.student_final_answer or "")
        self._symbol = infer_main_symbol(
            clause for text in texts for clause in split_implication_clauses(text)
        )
        return schema_q

    def _parse(self, text: str) -> ParsedStep:
        clauses = split_implication_clauses(text)
        source = clauses[-1] if len(clauses) > 1 else text
        return rebind_default_symbol(
            parse_math_step(source, self._symbol), source, self._symbol
        )

    def compare_first_step(
        self,
        question: Question,
    ) -> tuple[int, ValidationStatus, str] | None:
        """First written step must keep the stem's solution set.

        Returns ``(step_number, UNCERTAIN, reason)`` when it does not (or
        cannot be decided), else None. Only relational stems (equations /
        inequalities) are checked; unparseable stems are skipped.
        """
        schema_q = self._bind_symbol(question)
        if schema_q is None:
            return None
        stem_text = schema_stem_text(schema_q)
        first = next(
            (
                step
                for step in sorted(question.student_steps, key=lambda s: s.step_number)
                if not _is_figure_student_step(step) and _student_step_text(step)
            ),
            None,
        )
        if first is None or not stem_text:
            return None
        try:
            stem = self._parse(stem_text)
        except MathParseError:
            return None
        if stem.kind != "relation":
            return None
        clauses = split_implication_clauses(_student_step_text(first))
        try:
            student = self._parse(clauses[0] if clauses else _student_step_text(first))
        except MathParseError:
            return None
        result = self._equivalent(student, stem)
        if result is True:
            return None
        reason = (
            "first step does not keep the problem stem's solution set"
            if result is False
            else "could not compare first step to the problem stem"
        )
        return first.step_number, ValidationStatus.UNCERTAIN, reason

    def _unsolved_final_reason(
        self,
        student_step: ParsedStep,
        schema_q: ExamQuestion | None,
    ) -> str | None:
        """Reason when the final answer is not stated directly (copied stem / unfinished)."""
        if is_solved_form(student_step.kind, student_step.value, self._symbol):
            return None
        if schema_q is not None and student_step.kind == "relation":
            try:
                stem = self._parse(schema_stem_text(schema_q))
            except MathParseError:
                stem = None
            if (
                stem is not None
                and stem.kind == "relation"
                and isinstance(stem.value, Boolean)
                and isinstance(student_step.value, Boolean)
                and relations_form_equivalent(student_step.value, stem.value) is True
            ):
                return "final answer repeats the problem stem"
        return "final answer not in solved form"

    def compare(
        self,
        question: Question,
    ) -> tuple[ValidationStatus, str] | None:
        """Return (status, reason), or None if no schema question and no .tex."""
        schema_q = self._bind_symbol(question)
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
            student_step = self._parse(student_text)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse student final answer for standard compare",
            )

        try:
            standard_step = self._parse(standard_text)
        except MathParseError:
            return (
                ValidationStatus.UNCERTAIN,
                "could not parse standard final answer",
            )

        if is_solved_form(standard_step.kind, standard_step.value, self._symbol):
            unsolved = self._unsolved_final_reason(student_step, schema_q)
            if unsolved is not None:
                return ValidationStatus.UNCERTAIN, unsolved

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
        schema_q = self._bind_symbol(question)
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
        milestone_roles = frozenset(
            milestone.role.strip().lower()
            for milestone in (schema_q.milestones if schema_q is not None else [])
        )
        best: dict[int, tuple[ValidationStatus, str]] | None = None
        best_key: tuple[int, int] | None = None  # (valid, -invalid)

        for bank_id, standard_texts in banks:
            aligned = self._align_to_texts(
                student_steps,
                standard_texts,
                bank_id=bank_id,
                milestone_roles=milestone_roles,
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
    ) -> dict[str, tuple[ValidationStatus, str, float | None]]:
        """Coverage of student work vs schema milestones, keyed by milestone role.

        Scoring is keyed by rubric id, not by role: :func:`fold_role_marks`
        decides how roles land in buckets, so a rubric may give ``sign_chart``
        its own score or fold it back into ``critical_points``.
        """
        schema_q = self._bind_symbol(question)
        if schema_q is None or not schema_q.milestones:
            return {}

        role_results: dict[str, tuple[ValidationStatus, str, float | None]] = {}
        for milestone in schema_q.milestones:
            if milestone.role == HP_ROLE:
                continue
            mark = self._milestone_match(question, milestone)
            prev = role_results.get(milestone.role)
            if prev is None or _mark_fraction(mark) > _mark_fraction(prev):
                role_results[milestone.role] = mark
        return role_results

    def compare_figure(
        self,
        question: Question,
    ) -> tuple[ValidationStatus, str]:
        """Score figure part: number-line geometry vs schema, else human review."""
        schema_q = schema_question(self._schema, question.question_number)
        has_figure = _question_has_figure(question)
        expected = _expected_number_line(schema_q)

        if not has_figure:
            return ValidationStatus.INVALID, "no figure step"

        if expected is None:
            return ValidationStatus.UNCERTAIN, FIGURE_UNCOMPARED_REASON

        actual = _student_number_line(question)
        if actual is None:
            return (
                ValidationStatus.UNCERTAIN,
                "figure present but number_line unparseable",
            )
        return compare_number_lines(expected, actual)

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
        if milestone.role == SIGN_CHART_ROLE:
            sign_mark = _sign_pattern_match(question, texts)
            if sign_mark is not None:
                return sign_mark

        standard_parsed: list[ParsedStep] = []
        unparsed = 0
        for text in texts:
            try:
                standard_parsed.append(self._parse(text))
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

        student_pairs: list[tuple[StudentStep, ParsedStep]] = []
        for step in question.student_steps:
            if _is_figure_student_step(step):
                continue
            student_text = _student_step_text(step)
            if not student_text:
                continue
            try:
                student_pairs.append((step, self._parse(student_text)))
            except MathParseError:
                continue
        students = [parsed for _, parsed in student_pairs]

        if not unparsed:
            point_mark = self._point_set_match(milestone.role, standard_parsed, student_pairs)
            if point_mark is not None:
                return point_mark

        matched = 0
        saw_false = 0
        saw_undecided = 0
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
        if (
            milestone.role == SIGN_CHART_ROLE
            and matched == 0
            and len(evaluation_row_signs(texts)) >= 2
            and _question_has_figure(question)
            and not _role_steps(question, SIGN_CHART_ROLE)
        ):
            return (
                ValidationStatus.UNCERTAIN,
                SIGN_CHART_IN_FIGURE_REASON,
                None,
            )
        if saw_undecided or unparsed:
            # SymPy-undecided atoms earn half credit (as UNCERTAIN does); key
            # prose rows earn nothing but still send the mark to review.
            notes = []
            if saw_undecided:
                notes.append(f"{saw_undecided} undecided")
            if unparsed:
                notes.append(f"{unparsed} key rows undecided (prose, not scored)")
            return (
                ValidationStatus.UNCERTAIN,
                f"matches {matched}/{total} of milestone {milestone.role}; "
                + "; ".join(notes),
                (matched + 0.5 * saw_undecided) / total,
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

    def _points(self, parsed: ParsedStep) -> list[Expr] | None:
        """Finite, non-empty real solution points of a relation; else ``None``."""
        if parsed.kind != "relation" or not isinstance(parsed.value, Boolean):
            return None
        values = finite_solutions(parsed.value, self._symbol)
        if not isinstance(values, FiniteSet) or not values:
            return None
        return list(values)

    def _point_set_match(
        self,
        role: str,
        standard_parsed: list[ParsedStep],
        student_pairs: list[tuple[StudentStep, ParsedStep]],
    ) -> tuple[ValidationStatus, str, float | None] | None:
        """Compare point milestones as sets, so ``x=0 or x=1`` equals ``x=0; x=1``.

        Student points come from steps with this role (else every non-figure
        point step). Extra wrong points from role-tagged steps lower the score:
        ``|key ∩ student| / (|key| + |student − key|)``. Untagged steps only
        count hits, since an algebra equation like ``x = 3`` is not a stated
        critical point. ``None`` = not a point milestone (or no student points);
        the caller uses atom coverage instead.
        """
        key: list[Expr] = []
        for atom in standard_parsed:
            points = self._points(atom)
            if points is None:
                return None
            key = _add_points(key, points)

        tagged = [parsed for step, parsed in student_pairs if step.role == role]
        pool = tagged or [parsed for _, parsed in student_pairs]
        student: list[Expr] = []
        for parsed in pool:
            student = _add_points(student, self._points(parsed) or [])
        if not student:
            return None

        hits = sum(1 for point in key if _has_point(student, point))
        extra = (
            sum(1 for point in student if not _has_point(key, point)) if tagged else 0
        )
        total = len(key)
        source = "" if tagged else " (untagged steps)"
        if hits == total and extra == 0:
            return ValidationStatus.VALID, f"matches milestone {role}{source}", 1.0
        reason = f"matches {hits}/{total} of milestone {role}{source}"
        if extra:
            reason += f"; {extra} extra point(s)"
        return ValidationStatus.INVALID, reason, hits / (total + extra)

    def _align_to_texts(
        self,
        student_steps: list[StudentStep],
        standard_texts: list[str],
        *,
        bank_id: str,
        milestone_roles: frozenset[str] = frozenset(),
    ) -> dict[int, tuple[ValidationStatus, str]]:
        # Prose / unparseable key rows are not alignment targets; they keep
        # their original row number so labels still point into the key.
        standard_parsed: list[ParsedStep] = []
        column_numbers: list[int] = []
        for index, text in enumerate(standard_texts, start=1):
            if not text.strip():
                continue
            try:
                standard_parsed.append(self._parse(text))
            except MathParseError:
                continue
            column_numbers.append(index)

        rows: list[tuple[int, list[bool | None] | None]] = []
        skip_reasons: dict[int, str] = {}
        early: dict[int, tuple[ValidationStatus, str]] = {}

        for step in student_steps:
            role = (step.role or "").strip().lower()
            if role and role != HP_ROLE and role in milestone_roles:
                rows.append((step.step_number, None))
                skip_reasons[step.step_number] = f"scored under milestone {role}"
                continue
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
            rows, skip_reasons=skip_reasons, column_numbers=column_numbers
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
        standard_parsed: list[ParsedStep],
    ) -> _RowBuild:
        if step.role == "figure" or (
            step.symbolic is not None and step.symbolic.kind == "figure"
        ):
            return _RowBuild(
                kind="skip",
                reason="figure step skipped for standard align",
            )
        if (step.role or "").strip().lower() == HP_ROLE:
            return _RowBuild(kind="skip", reason=HP_ALIGN_SKIP_REASON)
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
            student_parsed = self._parse(student_text)
        except MathParseError:
            return _RowBuild(
                kind="skip",
                reason="could not parse student step for standard align",
            )

        row = [self._align_equivalent(student_parsed, std) for std in standard_parsed]
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


def _same_point(left: Expr, right: Expr) -> bool:
    try:
        return abs(complex(left) - complex(right)) < 1e-9
    except (TypeError, ValueError):
        return bool(left == right)


def _has_point(points: list[Expr], point: Expr) -> bool:
    return any(_same_point(existing, point) for existing in points)


def _add_points(points: list[Expr], new: list[Expr]) -> list[Expr]:
    merged = list(points)
    for point in new:
        if not _has_point(merged, point):
            merged.append(point)
    return merged


def _role_steps(question: Question, role: str) -> list[StudentStep]:
    return [
        step
        for step in question.student_steps
        if (step.role or "").strip().lower() == role
    ]


def _figure_texts(question: Question) -> list[str]:
    texts = [ref.caption or "" for ref in question.figure_refs]
    texts.extend(
        step.raw_text or ""
        for step in question.student_steps
        if _is_figure_student_step(step)
    )
    return [text for text in texts if text.strip()]


def _sign_pattern_match(
    question: Question, key_texts: list[str]
) -> tuple[ValidationStatus, str, float | None] | None:
    """Key sign pattern vs student sign rows, else figure caption; ``None`` = no evidence."""
    key = evaluation_row_signs(key_texts)
    if len(key) < 2:
        return None
    shown = format_signs(key)
    rows = evaluation_row_signs(
        _student_step_text(step) for step in _role_steps(question, SIGN_CHART_ROLE)
    )
    if len(rows) == len(key):
        if rows == key:
            return ValidationStatus.VALID, f"sign pattern matches key ({shown})", 1.0
        return (
            ValidationStatus.INVALID,
            f"sign pattern {format_signs(rows)} differs from key ({shown})",
            0.0,
        )
    for text in _figure_texts(question):
        if caption_signs(text) == key:
            return (
                ValidationStatus.VALID,
                f"figure sign pattern matches key ({shown})",
                1.0,
            )
    return None


def _student_step_text(step: StudentStep) -> str:
    if step.symbolic is not None and (step.symbolic.repr or "").strip():
        return step.symbolic.repr.strip()
    return (step.latex or "").strip() or (step.raw_text or "").strip()


def _question_has_figure(question: Question) -> bool:
    if question.figure_refs:
        return True
    return any(
        step.role == "figure"
        or (step.symbolic is not None and step.symbolic.kind == "figure")
        for step in question.student_steps
    )


def _expected_number_line(schema_q: ExamQuestion | None) -> NumberLineSpec | None:
    if schema_q is None:
        return None
    if schema_q.number_line is not None and schema_q.number_line.intervals:
        return schema_q.number_line
    # Interval HP on a non-figure question is not number-line geometry.
    if not schema_q.expects_figure:
        return None
    if schema_q.final_symbolic is not None:
        return number_line_from_symbolic(schema_q.final_symbolic)
    if (schema_q.final or "").strip():
        return number_line_from_symbolic(schema_q.final)
    return None


def _student_number_line(question: Question) -> NumberLineSpec | None:
    # Prefer explicit figure symbolic.repr over captions / inequalities.
    for ref in question.figure_refs:
        parsed = _figure_ref_symbolic_number_line(ref)
        if parsed is not None:
            return parsed
    for step in question.student_steps:
        if not _is_figure_student_step(step):
            continue
        if step.symbolic is not None and (step.symbolic.repr or "").strip():
            parsed = parse_number_line_intervals_only(step.symbolic.repr)
            if parsed is not None:
                return parsed
    for ref in question.figure_refs:
        parsed = _figure_ref_caption_number_line(ref)
        if parsed is not None:
            return parsed
    for step in question.student_steps:
        if not _is_figure_student_step(step):
            continue
        if (step.raw_text or "").strip():
            parsed = parse_number_line_intervals_only(step.raw_text)
            if parsed is not None:
                return parsed
    return None


def _is_figure_student_step(step: StudentStep) -> bool:
    return step.role == "figure" or (
        step.symbolic is not None and step.symbolic.kind == "figure"
    )


def _figure_ref_symbolic_number_line(ref: FigureRef) -> NumberLineSpec | None:
    if ref.symbolic is not None and (ref.symbolic.repr or "").strip():
        # Figure geometry only — reject algebraic inequalities as poison.
        return parse_number_line_intervals_only(ref.symbolic.repr)
    return None


def _figure_ref_caption_number_line(ref: FigureRef) -> NumberLineSpec | None:
    if (ref.caption or "").strip():
        # Captions must be interval / NUMBER_LINE geometry, not algebra.
        return parse_number_line_intervals_only(ref.caption)
    return None
