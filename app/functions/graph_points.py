"""Graph endpoint points for figure grading (pure FP; used when schema has them)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.models.exam_schema import GraphPoint
from app.models.validation import ValidationStatus

_GRAPH_POINTS_MARKER_RE = re.compile(
    r"^[ \t]*%[ \t]*graph_points[ \t]*:[ \t]*(?P<body>\S.*?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_GRAPH_POINTS_TOKEN_RE = re.compile(
    r"GRAPH_POINTS\s*\((?P<body>.*)\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_POINT_RE = re.compile(
    r"\(\s*(?P<x>[^,()]+?)\s*,\s*(?P<y>[^,()]+?)\s*,\s*"
    r"(?P<kind>open|closed|hollow|filled)\s*\)",
    re.IGNORECASE,
)
_DOMAIN_CLAIM_RE = re.compile(
    r"(?:^|;)\s*(?P<claim>D_?\s*f\s*=\s*[^;]+)",
    re.IGNORECASE,
)


def extract_marked_graph_points(tex: str) -> list[GraphPoint]:
    """Parse ``% graph_points: (x, y, open); …`` markers in kunci TeX."""
    points: list[GraphPoint] = []
    for match in _GRAPH_POINTS_MARKER_RE.finditer(tex or ""):
        points.extend(parse_graph_points_body(match.group("body")))
    return points


def parse_graph_points_repr(text: str) -> list[GraphPoint] | None:
    """Parse ``GRAPH_POINTS(...)`` or a bare list of ``(x, y, open|closed)``."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    wrapped = _GRAPH_POINTS_TOKEN_RE.match(cleaned)
    body = wrapped.group("body") if wrapped is not None else cleaned
    points = parse_graph_points_body(body)
    return points or None


def parse_graph_points_body(body: str) -> list[GraphPoint]:
    points: list[GraphPoint] = []
    for match in _POINT_RE.finditer(body or ""):
        kind = match.group("kind").lower()
        closed = kind in {"closed", "filled"}
        points.append(
            GraphPoint(
                x=_squash(match.group("x")),
                y=_squash(match.group("y")),
                closed=closed,
            )
        )
    return points


def graph_points_to_repr(points: Sequence[GraphPoint]) -> str:
    """Canonical token for recognition / audit."""
    parts = [
        f"({p.x},{p.y},{'closed' if p.closed else 'open'})" for p in points
    ]
    return f"GRAPH_POINTS({';'.join(parts)})"


def domain_claim_from_final(final_text: str) -> str | None:
    """Interval RHS of the first ``D_f = …`` claim (for number-line derivation)."""
    match = _DOMAIN_CLAIM_RE.search(final_text or "")
    if match is None:
        return None
    claim = _squash(match.group("claim"))
    if "=" in claim:
        return _squash(claim.rsplit("=", 1)[-1])
    return claim


def compare_graph_points(
    expected: Sequence[GraphPoint],
    actual: Sequence[GraphPoint],
) -> tuple[ValidationStatus, str]:
    """Set-equivalence of endpoint marks (order-free; open/closed must match)."""
    if not expected:
        return ValidationStatus.UNCERTAIN, "no key graph points to compare"
    left = {_point_key(p) for p in expected}
    right = {_point_key(p) for p in actual}
    if left == right:
        return ValidationStatus.VALID, "graph endpoints match key"
    missing = left - right
    extra = right - left
    bits: list[str] = []
    if missing:
        bits.append(f"missing {sorted(missing)}")
    if extra:
        bits.append(f"extra {sorted(extra)}")
    return ValidationStatus.INVALID, "graph endpoints differ: " + "; ".join(bits)


def _point_key(point: GraphPoint) -> tuple[str, str, bool]:
    return (_squash(point.x), _squash(point.y), point.closed)


def _squash(text: str) -> str:
    return " ".join((text or "").split()).replace(" ", "")
