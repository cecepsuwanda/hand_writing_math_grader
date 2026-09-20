from sympy import Eq, Lt, Symbol

from app.exceptions import MathParseError
from app.services.math.equivalence import relations_equivalent
from app.services.math.parser import normalize_math_text, parse_relation
import pytest


def test_normalize_strips_ampersand_and_prefix() -> None:
    assert normalize_math_text("Jawaban akhir: x &< 4") == "x < 4"


def test_parse_equation_and_inequality() -> None:
    x = Symbol("x")
    eq = parse_relation("2x+5=15", x)
    assert isinstance(eq, Eq)
    ineq = parse_relation("2x - 3 < 5", x)
    assert isinstance(ineq, Lt)


def test_parse_rejects_non_relation() -> None:
    with pytest.raises(MathParseError):
        parse_relation("just words without operators")


def test_equivalence_valid_equation_transform() -> None:
    x = Symbol("x")
    prev = parse_relation("2x+5=15", x)
    nxt = parse_relation("2x=10", x)
    assert relations_equivalent(prev, nxt, x) is True


def test_equivalence_invalid_equation_transform() -> None:
    x = Symbol("x")
    prev = parse_relation("2x+5=15", x)
    nxt = parse_relation("2x=20", x)
    assert relations_equivalent(prev, nxt, x) is False


def test_equivalence_inequality_chain() -> None:
    x = Symbol("x")
    a = parse_relation("2x-3<5", x)
    b = parse_relation("2x<8", x)
    c = parse_relation("x<4", x)
    assert relations_equivalent(a, b, x) is True
    assert relations_equivalent(b, c, x) is True


def test_parse_abs_forms() -> None:
    x = Symbol("x")
    plain = parse_relation("|x|<2", x)
    lvert = parse_relation(r"\lvert x\rvert < 2", x)
    abs_cmd = parse_relation(r"\abs{x}<2", x)
    assert "Abs" in str(plain)
    assert relations_equivalent(plain, lvert, x) is True
    assert relations_equivalent(plain, abs_cmd, x) is True


def test_equivalence_abs_less_than_compound() -> None:
    x = Symbol("x")
    abs_form = parse_relation("|x|<2", x)
    compound = parse_relation("-2<x<2", x)
    assert relations_equivalent(abs_form, compound, x) is True


def test_equivalence_abs_greater_than_or() -> None:
    x = Symbol("x")
    abs_form = parse_relation("|x|>2", x)
    disjunct = parse_relation("x<-2 or x>2", x)
    assert relations_equivalent(abs_form, disjunct, x) is True


def test_equivalence_abs_shifted_chain() -> None:
    x = Symbol("x")
    a = parse_relation("|x-1|<3", x)
    b = parse_relation("-3<x-1<3", x)
    c = parse_relation("-2<x<4", x)
    assert relations_equivalent(a, b, x) is True
    assert relations_equivalent(b, c, x) is True


def test_interval_membership_equivalent_to_compound() -> None:
    x = Symbol("x")
    membership = parse_relation(r"x \in (1,3)", x)
    compound = parse_relation("1<x<3", x)
    assert relations_equivalent(membership, compound, x) is True
    closed = parse_relation(r"x \in [0,2]", x)
    closed_ineq = parse_relation("0<=x<=2", x)
    assert relations_equivalent(closed, closed_ineq, x) is True


def test_domain_neq_equivalent_to_or() -> None:
    x = Symbol("x")
    neq = parse_relation(r"x \neq 1", x)
    disjunct = parse_relation("x<1 or x>1", x)
    assert relations_equivalent(neq, disjunct, x) is True


def test_expression_assignment_equivalence() -> None:
    from app.services.math.equivalence import expressions_equivalent
    from app.services.math.parser import parse_math_step

    x = Symbol("x")
    a = parse_math_step("(f+g)(x)=2x+1", x)
    b = parse_math_step("y=2x+1", x)
    c = parse_math_step("y=2x+2", x)
    assert a.kind == "expression" and b.kind == "expression"
    assert expressions_equivalent(a.value, b.value) is True
    assert expressions_equivalent(a.value, c.value) is False


def test_parse_limit_two_sided() -> None:
    from app.services.math.parser import LimitClaim, parse_math_step

    x = Symbol("x")
    step = parse_math_step(r"\lim_{x \to 1} (x^2-1)/(x-1)", x)
    assert step.kind == "limit"
    assert isinstance(step.value, LimitClaim)
    assert step.value.point == 1
    assert step.value.dir == "+-"
    ascii_step = parse_math_step("lim x->1 (x+1)", x)
    assert ascii_step.kind == "limit"


def test_limits_equivalent_cancel_chain() -> None:
    from app.services.math.equivalence import limits_equivalent
    from app.services.math.parser import parse_math_step

    x = Symbol("x")
    a = parse_math_step(r"\lim_{x \to 1} (x^2-1)/(x-1)", x)
    b = parse_math_step(r"\lim_{x \to 1} (x+1)", x)
    two = parse_math_step("2", x)
    three = parse_math_step("3", x)
    assert limits_equivalent(a.value, b.value) is True
    assert limits_equivalent(a.value, two.value) is True
    assert limits_equivalent(a.value, three.value) is False


def test_point_value_and_continuity() -> None:
    from app.services.math.equivalence import (
        continuity_limit_equals_value,
        point_value,
    )
    from app.services.math.parser import parse_math_step, try_parse_function_value_eq

    x = Symbol("x")
    simplified = parse_math_step(r"\lim_{x \to 1} (x+1)", x)
    assert point_value(simplified.value.expr, x, 1) == 2
    assert continuity_limit_equals_value(simplified.value, parse_math_step("2", x).value) is True

    hole = parse_math_step(r"\lim_{x \to 1} (x^2-1)/(x-1)", x)
    assert point_value(hole.value.expr, x, 1) is None
    assert continuity_limit_equals_value(hole.value, parse_math_step("2", x).value) is True

    fa = try_parse_function_value_eq("f(1)=2", x)
    assert fa is not None
    point, rhs = fa
    assert point == 1 and rhs == 2
    assert continuity_limit_equals_value(simplified.value, rhs, claimed_point=point) is True
    assert continuity_limit_equals_value(
        simplified.value,
        parse_math_step("3", x).value,
        claimed_point=1,
    ) is False


def test_parse_derivative_and_equivalence() -> None:
    from app.services.math.equivalence import derivatives_equivalent
    from app.services.math.parser import DerivativeClaim, parse_math_step

    x = Symbol("x")
    latex = parse_math_step(r"\frac{d}{dx}(x^2+3x)", x)
    ascii_form = parse_math_step("d/dx(x^2+3x)", x)
    assert latex.kind == "derivative"
    assert isinstance(latex.value, DerivativeClaim)
    assert ascii_form.kind == "derivative"
    result = parse_math_step("2x+3", x)
    wrong = parse_math_step("2x", x)
    primed = parse_math_step("y'=2x+3", x)
    assert primed.kind == "expression"
    assert derivatives_equivalent(latex.value, ascii_form.value) is True
    assert derivatives_equivalent(latex.value, result.value) is True
    assert derivatives_equivalent(latex.value, primed.value) is True
    assert derivatives_equivalent(latex.value, wrong.value) is False


def test_parse_integral_and_equivalence() -> None:
    from app.services.math.equivalence import integrals_equivalent
    from app.services.math.parser import IntegralClaim, parse_math_step

    x = Symbol("x")
    latex = parse_math_step(r"\int (2x+3)\,dx", x)
    ascii_form = parse_math_step("int (2x+3) dx", x)
    assert latex.kind == "integral"
    assert isinstance(latex.value, IntegralClaim)
    assert ascii_form.kind == "integral"
    with_c = parse_math_step("x^2+3x+C", x)
    without_c = parse_math_step("x^2+3x", x)
    wrong = parse_math_step("x^2", x)
    assert integrals_equivalent(latex.value, ascii_form.value) is True
    assert integrals_equivalent(latex.value, with_c.value) is True
    assert integrals_equivalent(latex.value, without_c.value) is True
    assert integrals_equivalent(latex.value, wrong.value) is False
    definite = parse_math_step(r"\int_{0}^{1}(2x)\,dx", x)
    assert definite.kind == "integral"
    assert definite.value.lower == 0 and definite.value.upper == 1
    assert integrals_equivalent(definite.value, parse_math_step("1", x).value) is True


def test_parse_transcendental_ln_exp() -> None:
    from app.services.math.equivalence import (
        derivatives_equivalent,
        expressions_equivalent,
        integrals_equivalent,
    )
    from app.services.math.parser import DerivativeClaim, IntegralClaim, parse_math_step

    x = Symbol("x")
    ln_diff = parse_math_step(r"\frac{d}{dx}(\ln x)", x)
    assert ln_diff.kind == "derivative"
    assert isinstance(ln_diff.value, DerivativeClaim)
    assert derivatives_equivalent(ln_diff.value, parse_math_step("1/x", x).value) is True
    assert derivatives_equivalent(ln_diff.value, parse_math_step("1/x^2", x).value) is False

    exp_diff = parse_math_step(r"\frac{d}{dx}(e^{2x})", x)
    assert exp_diff.kind == "derivative"
    assert derivatives_equivalent(
        exp_diff.value,
        parse_math_step(r"2e^{2x}", x).value,
    ) is True

    exp_int = parse_math_step(r"\int e^x\,dx", x)
    assert exp_int.kind == "integral"
    assert isinstance(exp_int.value, IntegralClaim)
    assert integrals_equivalent(exp_int.value, parse_math_step(r"e^x+C", x).value) is True

    assert expressions_equivalent(
        parse_math_step(r"e^{\ln x}", x).value,
        parse_math_step("x", x).value,
    ) is True
    assert expressions_equivalent(
        parse_math_step(r"\ln(e^x)", x).value,
        parse_math_step("x", x).value,
    ) is True


def test_parse_matrix_ops_and_equivalence() -> None:
    from app.services.math.equivalence import matrices_equivalent
    from app.services.math.parser import MatrixClaim, parse_math_step

    add = parse_math_step(
        r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}"
        r"+\begin{pmatrix}5 & 6 \\ 7 & 8\end{pmatrix}"
    )
    sum_m = parse_math_step(r"\begin{pmatrix}6 & 8 \\ 10 & 12\end{pmatrix}")
    wrong = parse_math_step(r"\begin{pmatrix}0 & 0 \\ 0 & 0\end{pmatrix}")
    assert add.kind == "matrix" and isinstance(add.value, MatrixClaim)
    assert matrices_equivalent(add.value, sum_m.value) is True
    assert matrices_equivalent(add.value, wrong.value) is False

    transpose = parse_math_step(r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}^{T}")
    expected_t = parse_math_step(r"\begin{pmatrix}1 & 3 \\ 2 & 4\end{pmatrix}")
    assert matrices_equivalent(transpose.value, expected_t.value) is True

    ascii_form = parse_math_step("[[1,2],[3,4]]")
    latex_form = parse_math_step(r"\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}")
    assert matrices_equivalent(ascii_form.value, latex_form.value) is True

    product = parse_math_step(
        r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}"
        r"\begin{pmatrix}0 & 1 \\ 1 & 0\end{pmatrix}"
    )
    expected_p = parse_math_step(r"\begin{pmatrix}2 & 1 \\ 4 & 3\end{pmatrix}")
    assert matrices_equivalent(product.value, expected_p.value) is True


def test_parse_det_and_inverse() -> None:
    from app.exceptions import MathParseError
    from app.services.math.equivalence import (
        expressions_equivalent,
        matrices_equivalent,
    )
    from app.services.math.parser import MatrixClaim, parse_math_step

    det = parse_math_step(r"\det\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}")
    vmat = parse_math_step(r"\begin{vmatrix}1 & 2 \\ 3 & 4\end{vmatrix}")
    two = parse_math_step("-2")
    wrong = parse_math_step("2")
    assert det.kind == "expression" and vmat.kind == "expression"
    assert expressions_equivalent(det.value, two.value) is True
    assert expressions_equivalent(vmat.value, two.value) is True
    assert expressions_equivalent(det.value, wrong.value) is False

    inv = parse_math_step(r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}^{-1}")
    expected = parse_math_step(r"\begin{pmatrix}-2 & 1 \\ 3/2 & -1/2\end{pmatrix}")
    assert inv.kind == "matrix" and isinstance(inv.value, MatrixClaim)
    assert matrices_equivalent(inv.value, expected.value) is True

    try:
        parse_math_step(r"\begin{pmatrix}1 & 0 \\ 0 & 0\end{pmatrix}^{-1}")
        assert False, "expected MathParseError for singular inverse"
    except MathParseError:
        pass


def test_parse_vector_norm_dot_and_unit() -> None:
    from app.services.math.equivalence import (
        expressions_equivalent,
        matrices_equivalent,
    )
    from app.services.math.parser import MatrixClaim, parse_math_step

    norm = parse_math_step(r"||<3,4>||")
    lvert = parse_math_step(r"\lVert\langle 3,4\rangle\rVert")
    five = parse_math_step("5")
    six = parse_math_step("6")
    assert norm.kind == "expression" and lvert.kind == "expression"
    assert expressions_equivalent(norm.value, five.value) is True
    assert expressions_equivalent(lvert.value, five.value) is True
    assert expressions_equivalent(norm.value, six.value) is False

    dot = parse_math_step(
        r"\begin{pmatrix}1 \\ 2\end{pmatrix}\cdot\begin{pmatrix}3 \\ 4\end{pmatrix}"
    )
    eleven = parse_math_step("11")
    assert dot.kind == "expression"
    assert expressions_equivalent(dot.value, eleven.value) is True

    unit = parse_math_step(r"<3,4>/||<3,4>||")
    expected = parse_math_step(r"\begin{pmatrix}3/5 \\ 4/5\end{pmatrix}")
    assert unit.kind == "matrix" and isinstance(unit.value, MatrixClaim)
    assert matrices_equivalent(unit.value, expected.value) is True

    # Angle brackets must not break ordinary inequalities
    rel = parse_math_step("1<x<3")
    assert rel.kind == "relation"
