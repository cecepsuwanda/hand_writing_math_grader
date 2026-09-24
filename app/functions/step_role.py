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


def coalesce_step_role(
    raw_text: str,
    symbolic: SymbolicPayload | None,
    role: StepRole | str | None,
) -> StepRole:
    """Return a concrete step role.

    An explicit non-algebra VLM role wins. ``algebra`` (the usual default)
    still yields to figure kind and to text inference.
    """
    if isinstance(role, str):
        normalized = role.strip().lower()
        if normalized in _VALID_ROLES and normalized != "algebra":
            return normalized  # type: ignore[return-value]

    if symbolic is not None and symbolic.kind == "figure":
        return "figure"

    blob = " ".join(
        part
        for part in (
            (raw_text or "").strip(),
            (symbolic.repr if symbolic is not None else "") or "",
        )
        if part
    )
    if not blob:
        return "algebra"

    if _FIGURE_RE.search(blob):
        return "figure"
    if _HP_RE.search(blob):
        return "hp"
    if _CRITICAL_RE.search(blob):
        return "critical_points"
    if _SIGN_RE.search(blob):
        return "sign_chart"
    return "algebra"
