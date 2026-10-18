"""Function-topic (bab 3) kunci helpers: prose, tabular pairs, markers (pure FP)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.functions.tex_tree import find_environment, remove_environments
from app.models.recognition import SymbolicPayload
from app.models.validation import ValidationStatus

_CONCEPT_MARKER_RE = re.compile(
    r"^[ \t]*%[ \t]*concept[ \t]*:[ \t]*(?P<body>\S.*?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_VALUE_TABLE_MARKER_RE = re.compile(
    r"^[ \t]*%[ \t]*value_table[ \t]*:[ \t]*(?P<body>\S.*?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_PAIR_RE = re.compile(
    r"\(\s*(?P<x>[^,()]+?)\s*,\s*(?P<y>[^,()]+?)\s*\)",
)
_DOMAIN_AND_RANGE_TITLE_RE = re.compile(
    r"^Domain\s+dan\s+Range\b",
    re.IGNORECASE,
)
_RANGE_LINE_RE = re.compile(
    r"\bR_?\s*(?:\{?\s*f\s*\}?|_\s*\{?\s*f\s*\}?|\{\s*f\s*\})\s*=|"
    r"\bR_?\s*\{\s*f\s*\\circ|"
    r"\bR_?\s*\{\s*g\s*\\circ|"
    r"\brange\b",
    re.IGNORECASE,
)
_DOMAIN_LINE_RE = re.compile(
    r"\bD_?\s*(?:\{?\s*f\s*\}?|_\s*\{?\s*f\s*\}?|\{\s*f\s*\})\s*=|"
    r"\bD_?\s*\{\s*f\s*\\circ|"
    r"\bD_?\s*\{\s*g\s*\\circ|"
    r"\bdomain\b|"
    r"\\geq\s*0|\\leq\s*0",
    re.IGNORECASE,
)
_NOISE_ENVS = ("align", "aligned", "equation", "tikzpicture", "tabular", "center")
_VALUE_TABLE_TOKEN_RE = re.compile(
    r"^VALUE_TABLE\s*\((?P<body>.*)\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_FX_EQ_RE = re.compile(
    r"f\s*\(\s*(?P<x>[^)]+)\s*\)\s*=\s*(?P<y>.+)",
    re.IGNORECASE,
)


def extract_marked_concepts(tex: str) -> list[str]:
    """Every ``% concept: <text>`` marker (checklist bullets)."""
    return [
        _squash(match.group("body"))
        for match in _CONCEPT_MARKER_RE.finditer(tex or "")
        if match.group("body").strip()
    ]


def extract_marked_value_table(tex: str) -> list[str]:
    """``% value_table: (x,y); …`` → list of ``f(x)=y`` / pair strings."""
    pairs: list[str] = []
    for match in _VALUE_TABLE_MARKER_RE.finditer(tex or ""):
        pairs.extend(_pairs_from_body(match.group("body")))
    return pairs


def extract_tabular_value_pairs(tex: str) -> list[str]:
    """Parse first ``tabular`` as value table: first/last math cells → pairs."""
    span = find_environment(tex or "", "tabular")
    if span is None:
        return []
    body = (tex or "")[span.body_start : span.body_end]
    # Drop column-spec ``{c|c|c}`` glued to the first row.
    body = re.sub(r"^\s*\{[^\}]*\}", "", body, count=1)
    pairs: list[str] = []
    for raw_row in body.split(r"\\"):
        row = _TEX_COMMENT_RE.sub("", raw_row)
        row = re.sub(r"\\hline\b", " ", row)
        row = _squash(row)
        if not row or "&" not in row:
            continue
        # Skip header rows that mention x / Potongan as labels only.
        cells = [_squash(c) for c in row.split("&")]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        if any(re.search(r"^\$?x\$?$", c, re.I) for c in cells):
            continue
        if any("potongan" in c.lower() for c in cells):
            continue
        if any(re.search(r"^\$?f\s*\(\s*x\s*\)\$?$", c, re.I) for c in cells):
            # Horizontal f(x) | v1 | v2 | … tables need % value_table markers.
            continue
        left, right = cells[0], cells[-1]
        left = left.strip("$")
        right = right.strip("$")
        if not left or not right:
            continue
        if "|" in left or "|" in right:
            continue
        pairs.append(f"({left}, {right})")
    return pairs


def extract_section_prose(tex: str) -> list[str]:
    """Prose after stripping align/tikz/tabular; unwrap ``$…$`` (keep tokens)."""
    cleaned = remove_environments(tex or "", _NOISE_ENVS)
    cleaned = _TEX_COMMENT_RE.sub("", cleaned)
    cleaned = re.sub(r"\\(?:textbf|emph|textit|reseteq)\s*\{[^{}]*\}", " ", cleaned)
    cleaned = re.sub(r"\\(?:quad|qquad|smallskip|medskip|bigskip|centering)\b", " ", cleaned)
    # Unwrap inline/display math so ``$a > 0$`` survives as ``a > 0``.
    cleaned = re.sub(r"\$\$([^$]*)\$\$", r" \1 ", cleaned)
    cleaned = re.sub(r"\$([^$]*)\$", r" \1 ", cleaned)
    cleaned = re.sub(r"\\\[([^\]]*)\\\]", r" \1 ", cleaned)
    # Split on sentence-ish boundaries.
    chunks: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", cleaned):
        text = _squash(part)
        if len(text) < 12:
            continue
        if re.fullmatch(r"[\d\s.,;:+\-*/=<>\\]+", text):
            continue
        chunks.append(text)
    return chunks


def parse_value_table_pairs(texts: Sequence[str]) -> list[tuple[str, str]]:
    """Extract ``(x, y)`` / ``f(x)=y`` pairs from milestone or student step texts."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for text in texts:
        blob = text or ""
        wrapped = _VALUE_TABLE_TOKEN_RE.match(_squash(blob))
        if wrapped is not None:
            blob = wrapped.group("body")
        for match in _PAIR_RE.finditer(blob):
            key = (_norm_coord(match.group("x")), _norm_coord(match.group("y")))
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                pairs.append(key)
        for match in _FX_EQ_RE.finditer(blob):
            key = (_norm_coord(match.group("x")), _norm_coord(match.group("y")))
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                pairs.append(key)
    return pairs


def value_table_to_repr(pairs: Sequence[tuple[str, str]]) -> str:
    """Canonical symbolic repr so ingest never parses ``(a,b)`` as an interval."""
    body = ";".join(f"({x},{y})" for x, y in pairs)
    return f"VALUE_TABLE({body})"


def value_table_symbolic_payload(steps: Sequence[str]) -> SymbolicPayload | None:
    """Build a non-interval payload for a value_table milestone."""
    pairs = parse_value_table_pairs(steps)
    if not pairs:
        return None
    return SymbolicPayload(kind="expression", repr=value_table_to_repr(pairs))


def value_table_step_payloads(steps: Sequence[str]) -> list[SymbolicPayload | None]:
    """One payload per step; pair rows stay ``VALUE_TABLE`` atoms, not inequalities."""
    out: list[SymbolicPayload | None] = []
    for step in steps:
        pairs = parse_value_table_pairs([step])
        if pairs:
            out.append(
                SymbolicPayload(
                    kind="expression",
                    repr=value_table_to_repr(pairs),
                )
            )
        else:
            out.append(None)
    return out


def compare_value_table_pairs(
    expected: Sequence[tuple[str, str]],
    actual: Sequence[tuple[str, str]],
) -> tuple[ValidationStatus, str, float | None]:
    """Set-equivalence of table points (order-free); fraction = hits / |key|."""
    if not expected:
        return ValidationStatus.UNCERTAIN, "no key value_table pairs", None
    left = set(expected)
    right = set(actual)
    hits = len(left & right)
    total = len(left)
    fraction = hits / total if total else None
    if left == right:
        return ValidationStatus.VALID, "matches milestone value_table", 1.0
    if hits == 0 and not right:
        return (
            ValidationStatus.INVALID,
            "no student step matches milestone value_table",
            0.0,
        )
    extra = len(right - left)
    reason = f"matches {hits}/{total} of milestone value_table"
    if extra:
        reason += f"; {extra} extra pair(s)"
    status = ValidationStatus.VALID if hits == total else ValidationStatus.INVALID
    if hits and hits < total:
        status = ValidationStatus.INVALID
    return status, reason, fraction


def _norm_coord(text: str) -> str:
    return _squash(text).replace(" ", "").replace("{,}", ".").replace(",", ".")


def is_domain_and_range_title(title: str) -> bool:
    return bool(_DOMAIN_AND_RANGE_TITLE_RE.match((title or "").strip()))


def split_domain_range_steps(steps: list[str]) -> tuple[list[str], list[str]]:
    """Partition mixed D_f / R_f steps; leftovers go to domain."""
    domain: list[str] = []
    range_steps: list[str] = []
    for step in steps:
        if _RANGE_LINE_RE.search(step) and not (
            _DOMAIN_LINE_RE.search(step) and "R_" not in step and "range" not in step.lower()
        ):
            # Prefer range when R_ clearly present.
            if re.search(r"\bR_|\brange\b", step, re.I):
                range_steps.append(step)
                continue
        if _DOMAIN_LINE_RE.search(step) or not _RANGE_LINE_RE.search(step):
            domain.append(step)
        else:
            range_steps.append(step)
    if not domain and not range_steps:
        return list(steps), []
    return domain, range_steps


def enrich_milestone_steps(role: str, section_own: str, align_steps: list[str]) -> list[str]:
    """Combine align rows with role-specific extractions from ``section_own``."""
    steps = list(align_steps)
    if role == "value_table":
        pairs = extract_tabular_value_pairs(section_own)
        if pairs:
            return pairs
        return steps
    if role == "concept":
        prose = extract_section_prose(section_own)
        # Align first (equations in concept sections are rare), then prose.
        return _unique(steps + prose)
    # domain / range / composition: keep align; append short prose cues.
    prose = extract_section_prose(section_own)
    return _unique(steps + prose)


def _pairs_from_body(body: str) -> list[str]:
    return [
        f"({_squash(m.group('x'))}, {_squash(m.group('y'))})"
        for m in _PAIR_RE.finditer(body or "")
    ]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _squash(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _squash(text: str) -> str:
    return " ".join((text or "").split())


_TEX_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
