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
