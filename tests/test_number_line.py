"""Unit tests for number-line derive / parse / compare."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.functions.kunci_ingest import (
    build_exam_question,
    ingest_kunci_tex,
    render_standard_solution_tex,
)
from app.functions.number_line import (
    compare_number_lines,
    number_line_from_symbolic,
    number_line_to_repr,
    parse_number_line_repr,
)
from app.models.exam_schema import ExamQuestion, ExamSchema, NumberLineSpec
from app.models.question import FigureRef, Question
from app.models.recognition import SymbolicPayload
from app.models.validation import ValidationStatus
from app.services.grading.standard_comparer import StandardFinalComparer


@pytest.mark.parametrize(
    ("text", "expected_repr"),
    [
        ("[-10/3, oo)", "NUMBER_LINE([-10/3,oo))"),
        ("NUMBER_LINE([-10/3,oo))", "NUMBER_LINE([-10/3,oo))"),
        ("(1, oo)", "NUMBER_LINE((1,oo))"),
        ("(-1/2, 2/3]", "NUMBER_LINE((-1/2,2/3])"),
        ("(-1/2, 3)", "NUMBER_LINE((-1/2,3))"),
        ("[-1, 6]", "NUMBER_LINE([-1,6])"),
        ("(-oo, -1) U (1/3, 3)", "NUMBER_LINE((-oo,-1)U(1/3,3))"),
        ("(-4, 0) U (2, oo)", "NUMBER_LINE((-4,0)U(2,oo))"),
        ("-10/3 <= x < oo", "NUMBER_LINE([-10/3,oo))"),
        ("1 < x < oo", "NUMBER_LINE((1,oo))"),
    ],
)
def test_parse_number_line_shapes(text: str, expected_repr: str) -> None:
    spec = parse_number_line_repr(text)
    assert spec is not None
    assert number_line_to_repr(spec) == expected_repr


def test_compare_equal_and_wrong_inclusion() -> None:
    expected = parse_number_line_repr("NUMBER_LINE([-10/3,oo))")
    assert expected is not None
    same = parse_number_line_repr("-((10)/(3)) <= x < oo")
    assert same is not None
    status, reason = compare_number_lines(expected, same)
    assert status == ValidationStatus.VALID
    assert "matches" in reason

    wrong = parse_number_line_repr("NUMBER_LINE((-10/3,oo))")
    assert wrong is not None
    status, reason = compare_number_lines(expected, wrong)
    assert status == ValidationStatus.INVALID
    assert "does not match" in reason


def test_number_line_from_symbolic_payload() -> None:
    payload = SymbolicPayload(kind="relation", repr="-((10)/(3)) <= x < oo")
    spec = number_line_from_symbolic(payload)
    assert spec is not None
    assert len(spec.intervals) == 1
    assert spec.intervals[0].left is not None
    assert spec.intervals[0].left.closed is True
    assert spec.intervals[0].right is None


_MINI_WITH_TIKZ = r"""
\begin{enumerate}
\item $2-3x \le 12$
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah-langkah Penyelesaian
\begin{align}
2 - 3x &\leq 12 \\
x &\geq -\frac{10}{3}
\end{align}
\item Gambar Garis Bilangan
\begin{tikzpicture}
\draw (-1,0)--(1,0);
\end{tikzpicture}
\item HP: $\left[-\frac{10}{3}, \infty\right)$
\end{itemize}
\end{enumerate}
"""


def test_ingest_sets_number_line_and_solution_comment() -> None:
    items = __import__(
        "app.functions.kunci_ingest", fromlist=["split_enumerate_items"]
    ).split_enumerate_items(_MINI_WITH_TIKZ)
    q = build_exam_question(1, items[0])
    assert q is not None
    assert q.expects_figure is True
    assert q.number_line is not None
    assert q.number_line.intervals
    assert q.number_line.intervals[0].left is not None
    assert q.number_line.intervals[0].left.closed is True

    rendered = render_standard_solution_tex(question=q, final=q.final)
    assert "% role: figure" in rendered
    assert "% number_line: NUMBER_LINE(" in rendered

    pairs = ingest_kunci_tex(_MINI_WITH_TIKZ, source_note="mini")
    assert pairs
    assert "% number_line:" in pairs[0][1]


def test_compare_figure_semantic(tmp_path: Path) -> None:
    expected = parse_number_line_repr("NUMBER_LINE([-10/3,oo))")
    assert expected is not None
    schema = ExamSchema(
        source="test",
        questions=[
            ExamQuestion(
                number=1,
                stem="$2-3x\\le 12$",
                final=r"\left[-\frac{10}{3}, \infty\right)",
                expects_figure=True,
                number_line=expected,
            )
        ],
    )
    comparer = StandardFinalComparer(tmp_path, exam_schema=schema)

    good = Question(
        question_id="question_001",
        question_number=1,
        figure_refs=[
            FigureRef(
                path="fig.png",
                caption="closed at -10/3 ray right",
                symbolic=SymbolicPayload(
                    kind="figure",
                    repr="NUMBER_LINE([-10/3,oo))",
                ),
            )
        ],
    )
    status, reason = comparer.compare_figure(good)
    assert status == ValidationStatus.VALID
    assert "matches" in reason

    bad = Question(
        question_id="question_001",
        question_number=1,
        figure_refs=[
            FigureRef(
                path="fig.png",
                caption="open circle",
                symbolic=SymbolicPayload(
                    kind="figure",
                    repr="NUMBER_LINE((-10/3,oo))",
                ),
            )
        ],
    )
    status, reason = comparer.compare_figure(bad)
    assert status == ValidationStatus.INVALID

    missing = Question(question_id="question_001", question_number=1)
    status, reason = comparer.compare_figure(missing)
    assert status == ValidationStatus.INVALID
    assert reason == "no figure step"

    unparsed = Question(
        question_id="question_001",
        question_number=1,
        figure_refs=[
            FigureRef(path="fig.png", caption="some scribbles only"),
        ],
    )
    status, reason = comparer.compare_figure(unparsed)
    assert status == ValidationStatus.UNCERTAIN
    assert "unparseable" in reason


def test_prose_with_embedded_interval_is_not_a_number_line() -> None:
    assert parse_number_line_repr("titik (1, 0)") is None
    assert parse_number_line_repr("lihat (1, 2) di sumbu") is None


def test_descending_chain_matches_ascending_interval() -> None:
    spec = parse_number_line_repr("2/3 >= x > -1/2")
    assert spec is not None
    assert number_line_to_repr(spec) == "NUMBER_LINE((-1/2,2/3])"
    keyed = parse_number_line_repr("((2)/(3)) >= x > -((1)/(2))")
    assert keyed is not None
    assert number_line_to_repr(keyed) == "NUMBER_LINE((-1/2,2/3])"
    assert parse_number_line_repr("1 < x > 0") is None


def test_union_order_does_not_change_equivalence() -> None:
    expected = parse_number_line_repr("NUMBER_LINE((-oo,-1)U(1/3,3))")
    flipped = parse_number_line_repr("NUMBER_LINE((1/3,3)U(-oo,-1))")
    assert expected is not None and flipped is not None
    status, reason = compare_number_lines(expected, flipped)
    assert status == ValidationStatus.VALID
    assert "matches" in reason


def test_compare_figure_ignores_interval_final_when_figure_not_expected(
    tmp_path: Path,
) -> None:
    schema = ExamSchema(
        source="legacy",
        questions=[
            ExamQuestion(
                number=1,
                stem="s",
                final=r"(1, \infty)",
                final_symbolic=SymbolicPayload(kind="relation", repr="1 < x < oo"),
                expects_figure=False,
                number_line=None,
            )
        ],
    )
    comparer = StandardFinalComparer(tmp_path, exam_schema=schema)
    drawn = Question(
        question_id="question_001",
        question_number=1,
        figure_refs=[
            FigureRef(
                path="fig.png",
                caption="open ray",
                symbolic=SymbolicPayload(
                    kind="figure",
                    repr="NUMBER_LINE((-10/3,oo))",
                ),
            )
        ],
    )
    status, reason = comparer.compare_figure(drawn)
    assert status == ValidationStatus.VALID
    assert reason == "figure step present"


def test_compare_figure_presence_fallback_without_number_line(
    tmp_path: Path,
) -> None:
    schema = ExamSchema(
        source="legacy",
        questions=[
            ExamQuestion(
                number=1,
                stem="s",
                expects_figure=True,
                number_line=None,
            )
        ],
    )
    comparer = StandardFinalComparer(tmp_path, exam_schema=schema)
    q = Question(
        question_id="question_001",
        question_number=1,
        figure_refs=[FigureRef(path="f.png", caption="diagram")],
    )
    status, reason = comparer.compare_figure(q)
    assert status == ValidationStatus.VALID
    assert reason == "figure step present"
