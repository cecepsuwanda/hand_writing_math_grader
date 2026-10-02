"""SymPy-first step validator (no LLM)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from sympy import Eq, Expr, S, Symbol
from sympy.core.relational import Relational
from sympy.logic.boolalg import Boolean

from app.exceptions import MathParseError
from app.functions.step_references import (
    final_reference_index,
    reference_indices,
    step_checks_for,
)
from app.interfaces.validator import StepValidator
from app.models.question import Question, StudentStep
from app.models.validation import (
    QuestionValidation,
    StepCheck,
    StepValidation,
    ValidationMethod,
    ValidationStatus,
)
from app.services.math.equivalence import (
    continuity_limit_equals_value,
    derivatives_equivalent,
    expressions_equivalent,
    integrals_equivalent,
    limits_equivalent,
    matrices_equivalent,
    relations_equivalent,
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
    try_parse_function_value_eq,
)
from app.services.math.role_checks import (
    finite_solutions,
    numeric_relation_holds,
    values_are_zero_makers,
)

logger = logging.getLogger(__name__)

_StepChecker = Callable[[StudentStep, ParsedStep | None, ParsedStep | None], StepValidation]


class SymPyStepValidator(StepValidator):
    def __init__(
        self,
        symbol: Symbol | None = None,
        step_checks: Mapping[str, StepCheck] | None = None,
    ) -> None:
        self._symbol = symbol or default_symbol()
        self._step_checks = dict(step_checks or {})
        self._checkers: dict[StepCheck, _StepChecker] = {
            StepCheck.TRANSITION: self._validate_transition,
            StepCheck.ZERO_MAKERS: self._check_zero_makers,
            StepCheck.NUMERIC_EVAL: self._check_numeric_eval,
            StepCheck.SOLUTION_SET: self._check_solution_set,
            StepCheck.NOT_SYMBOLIC: self._check_not_symbolic,
        }

    def validate_question(self, question: Question) -> QuestionValidation:
        steps = sorted(question.student_steps, key=lambda s: s.step_number)
        checks = step_checks_for([step.role for step in steps], self._step_checks)
        parsed = [self._try_parse(step) for step in steps]
        step_results = [
            self._validate_step(
                step,
                check,
                reference=None if ref is None else parsed[ref],
                current=parsed[index],
                has_reference=ref is not None,
            )
            for index, (step, check, ref) in enumerate(
                zip(steps, checks, reference_indices(checks))
            )
        ]

        final_status = None
        final_text = ""
        if (
            question.student_final_symbolic is not None
            and (question.student_final_symbolic.repr or "").strip()
        ):
            final_text = question.student_final_symbolic.repr.strip()
        elif (question.student_final_answer or "").strip():
            final_text = question.student_final_answer.strip()
        if final_text and steps:
            final_ref = final_reference_index(checks)
            final_status = self._validate_final_answer(
                final_text,
                None if final_ref is None else parsed[final_ref],
                last_step_number=steps[-1].step_number,
            )

        result = QuestionValidation(
            question_number=question.question_number,
            question_id=question.question_id,
            steps=step_results,
            final_answer_status=final_status,
        )
        logger.info(
            "Validated %s: %s",
            question.question_id,
            [s.status.value for s in step_results],
        )
        return result

    def _step_expression(self, step: StudentStep) -> str:
        if step.symbolic is not None and (step.symbolic.repr or "").strip():
            return step.symbolic.repr.strip()
        latex = (step.latex or "").strip()
        if latex:
            return latex
        return (step.raw_text or "").strip()

    def _try_parse(self, step: StudentStep) -> ParsedStep | None:
        if step.symbolic is not None and step.symbolic.kind == "figure":
            return None
        expression = self._step_expression(step)
        if not expression:
            return None
        try:
            return parse_math_step(expression, self._symbol)
        except MathParseError:
            return None

    def _validate_first(
        self,
        step: StudentStep,
        item: ParsedStep | None,
    ) -> StepValidation:
        if step.symbolic is not None and step.symbolic.kind == "figure":
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="figure/graph step is not SymPy-checkable",
            )
        if item is None:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="could not parse first step",
            )
        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.VALID,
            method=ValidationMethod.PARSE,
            reason="first step parsed successfully",
        )

    def _validate_step(
        self,
        step: StudentStep,
        check: StepCheck,
        *,
        reference: ParsedStep | None,
        current: ParsedStep | None,
        has_reference: bool,
    ) -> StepValidation:
        if check == StepCheck.TRANSITION:
            if not has_reference:
                return self._validate_first(step, current)
            return self._validate_transition(step, reference, current)
        result = self._checkers[check](step, reference, current)
        return result.model_copy(update={"reason": f"{check.value}: {result.reason}"})

    def _check_zero_makers(
        self,
        step: StudentStep,
        reference: ParsedStep | None,
        current: ParsedStep | None,
    ) -> StepValidation:
        if current is None or current.kind != "relation":
            return self._uncertain(step, "could not parse zero-maker step")
        assert isinstance(current.value, Boolean)
        values = finite_solutions(current.value, self._symbol)
        if values is None:
            # Not a list of points (mislabelled role): judge it as an ordinary transition.
            return self._validate_transition(step, reference, current)
        if values is S.EmptySet:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.INVALID,
                method=ValidationMethod.SYMPY,
                reason="stated equations have no common solution",
            )
        if reference is None or reference.kind != "relation":
            return self._uncertain(step, "no parseable reference inequality")
        assert isinstance(reference.value, Boolean)
        return self._status_from_bool(
            step.step_number,
            values_are_zero_makers(values, reference.value, self._symbol),
            ok="values are zero-makers of the reference inequality",
            bad="a value is not a zero-maker of the reference inequality",
            unsure="SymPy could not find zero-makers of the reference inequality",
        )

    def _check_numeric_eval(
        self,
        step: StudentStep,
        reference: ParsedStep | None,
        current: ParsedStep | None,
    ) -> StepValidation:
        if current is None or current.kind != "relation":
            return self._uncertain(step, "could not parse numeric evaluation")
        assert isinstance(current.value, Boolean)
        return self._status_from_bool(
            step.step_number,
            numeric_relation_holds(current.value),
            ok="numeric evaluation is correct",
            bad="numeric evaluation is wrong",
            unsure="step is not a closed numeric evaluation",
        )

    def _check_solution_set(
        self,
        step: StudentStep,
        reference: ParsedStep | None,
        current: ParsedStep | None,
    ) -> StepValidation:
        if reference is None:
            return self._uncertain(step, "no parseable reference inequality")
        return self._validate_transition(step, reference, current)

    def _check_not_symbolic(
        self,
        step: StudentStep,
        reference: ParsedStep | None,
        current: ParsedStep | None,
    ) -> StepValidation:
        return self._uncertain(step, "figure/graph step is not SymPy-checkable")

    def _uncertain(self, step: StudentStep, reason: str) -> StepValidation:
        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.PARSE,
            reason=reason,
        )

    def _validate_transition(
        self,
        step: StudentStep,
        previous: ParsedStep | None,
        current: ParsedStep | None,
    ) -> StepValidation:
        if previous is None or current is None:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="could not parse step for SymPy comparison",
            )

        if previous.kind == "limit" or current.kind == "limit":
            return self._validate_limit_transition(step, previous, current)

        if previous.kind == "derivative" or current.kind == "derivative":
            return self._validate_derivative_transition(step, previous, current)

        if previous.kind == "integral" or current.kind == "integral":
            return self._validate_integral_transition(step, previous, current)

        if previous.kind == "matrix" or current.kind == "matrix":
            return self._validate_matrix_transition(step, previous, current)

        applicable, set_result = try_set_form_equivalence(
            previous.kind,
            previous.value,
            current.kind,
            current.value,
            self._symbol,
        )
        if applicable:
            return self._status_from_bool(
                step.step_number,
                set_result,
                ok="solution sets are equivalent",
                bad="solution sets differ",
                unsure="SymPy could not decide set equivalence",
            )

        if previous.kind != current.kind:
            return StepValidation(
                step_number=step.step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.SYMPY,
                reason="cannot compare steps of different kinds",
            )

        if previous.kind == "relation":
            assert isinstance(previous.value, Boolean)
            assert isinstance(current.value, Boolean)
            return self._status_from_bool(
                step.step_number,
                relations_equivalent(previous.value, current.value, self._symbol),
                ok="solution sets are equivalent",
                bad="solution sets differ",
                unsure="SymPy could not decide equivalence",
            )

        assert isinstance(previous.value, Expr)
        assert isinstance(current.value, Expr)
        fa = try_parse_function_value_eq(self._step_expression(step), self._symbol)
        if fa is not None:
            _point, rhs = fa
            return self._status_from_bool(
                step.step_number,
                expressions_equivalent(previous.value, rhs),
                ok="expression equals f(a) value",
                bad="expression differs from f(a) value",
                unsure="SymPy could not compare expression to f(a)",
            )
        return self._status_from_bool(
            step.step_number,
            expressions_equivalent(previous.value, current.value),
            ok="expressions are equivalent",
            bad="expressions differ",
            unsure="SymPy could not decide expression equivalence",
        )

    def _validate_limit_transition(
        self,
        step: StudentStep,
        previous: ParsedStep,
        current: ParsedStep,
    ) -> StepValidation:
        if previous.kind == "limit" and current.kind == "limit":
            assert isinstance(previous.value, LimitClaim)
            assert isinstance(current.value, LimitClaim)
            return self._status_from_bool(
                step.step_number,
                limits_equivalent(previous.value, current.value),
                ok="limits are equivalent",
                bad="limits differ",
                unsure="SymPy could not decide limit equivalence",
            )

        if previous.kind == "limit" and current.kind == "expression":
            assert isinstance(previous.value, LimitClaim)
            assert isinstance(current.value, Expr)
            fa = try_parse_function_value_eq(self._step_expression(step), self._symbol)
            if fa is not None:
                claimed_point, rhs = fa
                return self._status_from_bool(
                    step.step_number,
                    continuity_limit_equals_value(
                        previous.value,
                        rhs,
                        claimed_point=claimed_point,
                    ),
                    ok="limit equals f(a) (continuity at point)",
                    bad="limit differs from f(a) or point plug-in fails",
                    unsure="SymPy could not decide continuity at point",
                )
            return self._status_from_bool(
                step.step_number,
                limits_equivalent(previous.value, current.value),
                ok="limit equals expression value",
                bad="limit differs from expression value",
                unsure="SymPy could not compare limit to value",
            )

        if previous.kind == "limit" and current.kind == "relation":
            value = self._relation_rhs_value(current.value)
            if value is None:
                return StepValidation(
                    step_number=step.step_number,
                    status=ValidationStatus.UNCERTAIN,
                    method=ValidationMethod.SYMPY,
                    reason="cannot peel relation RHS for limit comparison",
                )
            assert isinstance(previous.value, LimitClaim)
            return self._status_from_bool(
                step.step_number,
                limits_equivalent(previous.value, value),
                ok="limit equals relation RHS",
                bad="limit differs from relation RHS",
                unsure="SymPy could not compare limit to relation RHS",
            )

        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.SYMPY,
            reason="cannot compare non-limit step into a limit step",
        )

    def _validate_derivative_transition(
        self,
        step: StudentStep,
        previous: ParsedStep,
        current: ParsedStep,
    ) -> StepValidation:
        if previous.kind == "derivative" and current.kind == "derivative":
            assert isinstance(previous.value, DerivativeClaim)
            assert isinstance(current.value, DerivativeClaim)
            return self._status_from_bool(
                step.step_number,
                derivatives_equivalent(previous.value, current.value),
                ok="derivatives are equivalent",
                bad="derivatives differ",
                unsure="SymPy could not decide derivative equivalence",
            )

        if previous.kind == "derivative" and current.kind == "expression":
            assert isinstance(previous.value, DerivativeClaim)
            assert isinstance(current.value, Expr)
            return self._status_from_bool(
                step.step_number,
                derivatives_equivalent(previous.value, current.value),
                ok="derivative equals expression",
                bad="derivative differs from expression",
                unsure="SymPy could not compare derivative to expression",
            )

        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.SYMPY,
            reason="cannot compare non-derivative step into a derivative step",
        )

    def _validate_integral_transition(
        self,
        step: StudentStep,
        previous: ParsedStep,
        current: ParsedStep,
    ) -> StepValidation:
        if previous.kind == "integral" and current.kind == "integral":
            assert isinstance(previous.value, IntegralClaim)
            assert isinstance(current.value, IntegralClaim)
            return self._status_from_bool(
                step.step_number,
                integrals_equivalent(previous.value, current.value),
                ok="integrals are equivalent",
                bad="integrals differ",
                unsure="SymPy could not decide integral equivalence",
            )

        if previous.kind == "integral" and current.kind == "expression":
            assert isinstance(previous.value, IntegralClaim)
            assert isinstance(current.value, Expr)
            return self._status_from_bool(
                step.step_number,
                integrals_equivalent(previous.value, current.value),
                ok="integral equals expression",
                bad="integral differs from expression",
                unsure="SymPy could not compare integral to expression",
            )

        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.SYMPY,
            reason="cannot compare non-integral step into an integral step",
        )

    def _validate_matrix_transition(
        self,
        step: StudentStep,
        previous: ParsedStep,
        current: ParsedStep,
    ) -> StepValidation:
        if previous.kind == "matrix" and current.kind == "matrix":
            assert isinstance(previous.value, MatrixClaim)
            assert isinstance(current.value, MatrixClaim)
            return self._status_from_bool(
                step.step_number,
                matrices_equivalent(previous.value, current.value),
                ok="matrices are equivalent",
                bad="matrices differ",
                unsure="SymPy could not decide matrix equivalence",
            )

        return StepValidation(
            step_number=step.step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.SYMPY,
            reason="cannot compare non-matrix step into a matrix step",
        )

    def _relation_rhs_value(
        self,
        value: Boolean | Expr | LimitClaim | DerivativeClaim | IntegralClaim,
    ) -> Expr | None:
        if isinstance(value, Eq):
            return value.rhs  # type: ignore[return-value]
        if isinstance(value, Relational) and value.rel_op == "==":
            return value.rhs  # type: ignore[return-value]
        return None

    def _status_from_bool(
        self,
        step_number: int,
        equivalent: bool | None,
        *,
        ok: str,
        bad: str,
        unsure: str,
    ) -> StepValidation:
        if equivalent is True:
            return StepValidation(
                step_number=step_number,
                status=ValidationStatus.VALID,
                method=ValidationMethod.SYMPY,
                reason=ok,
            )
        if equivalent is False:
            return StepValidation(
                step_number=step_number,
                status=ValidationStatus.INVALID,
                method=ValidationMethod.SYMPY,
                reason=bad,
            )
        return StepValidation(
            step_number=step_number,
            status=ValidationStatus.UNCERTAIN,
            method=ValidationMethod.SYMPY,
            reason=unsure,
        )

    def _validate_final_answer(
        self,
        final_answer: str,
        reference_item: ParsedStep | None,
        last_step_number: int,
    ) -> StepValidation:
        try:
            final_item = parse_math_step(final_answer, self._symbol)
        except MathParseError:
            return StepValidation(
                step_number=last_step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="could not parse final answer",
            )
        if reference_item is None:
            return StepValidation(
                step_number=last_step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.PARSE,
                reason="reference step not parseable for final-answer check",
            )

        if reference_item.kind == "limit":
            fake_step = StudentStep(step_number=last_step_number, raw_text="", latex="")
            return self._validate_limit_transition(fake_step, reference_item, final_item)

        if reference_item.kind == "derivative":
            fake_step = StudentStep(step_number=last_step_number, raw_text="", latex="")
            return self._validate_derivative_transition(fake_step, reference_item, final_item)

        if reference_item.kind == "integral":
            fake_step = StudentStep(step_number=last_step_number, raw_text="", latex="")
            return self._validate_integral_transition(fake_step, reference_item, final_item)

        if reference_item.kind == "matrix":
            fake_step = StudentStep(step_number=last_step_number, raw_text="", latex="")
            return self._validate_matrix_transition(fake_step, reference_item, final_item)

        applicable, set_result = try_set_form_equivalence(
            reference_item.kind,
            reference_item.value,
            final_item.kind,
            final_item.value,
            self._symbol,
        )
        if applicable:
            return self._status_from_bool(
                last_step_number,
                set_result,
                ok="final answer matches reference step solution set",
                bad="final answer solution set differs from reference step",
                unsure="SymPy could not compare final answer set",
            )

        if reference_item.kind != final_item.kind:
            return StepValidation(
                step_number=last_step_number,
                status=ValidationStatus.UNCERTAIN,
                method=ValidationMethod.SYMPY,
                reason="final answer kind differs from reference step",
            )

        if reference_item.kind == "relation":
            assert isinstance(reference_item.value, Boolean)
            assert isinstance(final_item.value, Boolean)
            return self._status_from_bool(
                last_step_number,
                relations_equivalent(reference_item.value, final_item.value, self._symbol),
                ok="final answer matches reference step solution set",
                bad="final answer solution set differs from reference step",
                unsure="SymPy could not compare final answer",
            )

        assert isinstance(reference_item.value, Expr)
        assert isinstance(final_item.value, Expr)
        return self._status_from_bool(
            last_step_number,
            expressions_equivalent(reference_item.value, final_item.value),
            ok="final answer matches reference step expression",
            bad="final answer expression differs from reference step",
            unsure="SymPy could not compare final answer expression",
        )
