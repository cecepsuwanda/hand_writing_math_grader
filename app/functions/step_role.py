"""Infer / coalesce step roles for recognition → grading (pure FP)."""

from __future__ import annotations

import re

from app.models.recognition import StepRole, SymbolicPayload

_VALID_ROLES: frozenset[str] = frozenset(
    {"algebra", "critical_points", "sign_chart", "figure", "hp"}
)

# Optional lead-in (Jadi/Maka/…) so "Jadi HP = ..." is still an answer set.
_HP_RE = re.compile(
    r"(?:^|\b(?:jadi|maka|sehingga|diperoleh)\s+)"
    r"(?:HP|himpunan\s+penyelesaian)\b",
    re.IGNORECASE,
)
_LEADIN_RE = re.compile(
    r"^\s*(?:jadi|maka|sehingga|diperoleh)\b\s*",
    re.IGNORECASE,
)
_PURE_INTERVAL_RE = re.compile(
    r"^\s*[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[\])]"
    r"(?:\s*(?:U|or|\\cup|∪)\s*[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[\])])*"
    r"\s*$",
    re.IGNORECASE,
)
_WHOLE_MEMBERSHIP_RE = re.compile(
    r"^\s*(?:(?:jadi|maka|sehingga|diperoleh)\s+)?"
    r"[A-Za-z][A-Za-z0-9_]*\s*(?:\\in|∈)\s*"
    r"[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[])](?:\s*(?:U|or|\\cup|∪)\s*"
    r"[\[(]\s*[^,]+?\s*,\s*[^)\]]+?\s*[])])*"
    r"\s*$",
    re.IGNORECASE,
)
_NUMBER_LINE_RE = re.compile(r"NUMBER_LINE\s*\(", re.IGNORECASE)
_CRITICAL_RE = re.compile(
    r"titik\s+(?:kritis|potong)|critical\s+points?|pembuat\s+nol",
    re.IGNORECASE,
)
_SIGN_RE = re.compile(
    r"analisis\s+tanda|sign\s+chart|uji\s+selang",
    re.IGNORECASE,
)
_FIGURE_RE = re.compile(
    r"garis\s+bilangan|number\s+line|\bdiagram\b|\bgraph\b|\bfigure\b",
    re.IGNORECASE,
)


def _blob(raw_text: str, symbolic: SymbolicPayload | None) -> str:
    return " ".join(
        part
        for part in (
            (raw_text or "").strip(),
            (symbolic.repr if symbolic is not None else "") or "",
        )
        if part
    )


def _strong_figure(raw_text: str, symbolic: SymbolicPayload | None) -> bool:
    if symbolic is not None and symbolic.kind == "figure":
        return True
    repr_text = (symbolic.repr if symbolic is not None else "") or ""
    if _NUMBER_LINE_RE.search(repr_text) or _NUMBER_LINE_RE.search(raw_text or ""):
        return True
    return bool(_FIGURE_RE.search(_blob(raw_text, symbolic)))


def _strong_hp(raw_text: str, symbolic: SymbolicPayload | None) -> bool:
    """Explicit HP / himpunan penyelesaian wording."""
    blob = _blob(raw_text, symbolic)
    return bool(blob and _HP_RE.search(blob))


def _weak_hp(raw_text: str, symbolic: SymbolicPayload | None) -> bool:
    """Interval / membership as the whole step content (not mid-prose)."""
    raw = (raw_text or "").strip()
    repr_text = ((symbolic.repr if symbolic is not None else "") or "").strip()

    if raw and _PURE_INTERVAL_RE.match(raw):
        return True
    if repr_text and _PURE_INTERVAL_RE.match(repr_text):
        return True
    if raw and _WHOLE_MEMBERSHIP_RE.match(raw):
        return True
    if repr_text and _WHOLE_MEMBERSHIP_RE.match(repr_text):
        return True
    if raw:
        remainder = _LEADIN_RE.sub("", raw, count=1).strip()
        if remainder and remainder != raw and _PURE_INTERVAL_RE.match(remainder):
            return True
    return False


def coalesce_step_role(
    raw_text: str,
    symbolic: SymbolicPayload | None,
    role: StepRole | str | None,
) -> StepRole:
    """Return a concrete step role.

    Strong figure / explicit HP override a conflicting VLM role. Explicit
    non-algebra VLM roles and critical/sign text beat weak HP signals
    (bare intervals / whole-step membership). ``algebra`` yields to heuristics.
    """
    if _strong_figure(raw_text, symbolic):
        return "figure"
    if _strong_hp(raw_text, symbolic):
        return "hp"

    if isinstance(role, str):
        normalized = role.strip().lower()
        if normalized in _VALID_ROLES and normalized != "algebra":
            return normalized  # type: ignore[return-value]

    blob = _blob(raw_text, symbolic)
    if blob:
        if _CRITICAL_RE.search(blob):
            return "critical_points"
        if _SIGN_RE.search(blob):
            return "sign_chart"

    if _weak_hp(raw_text, symbolic):
        return "hp"
    return "algebra"
