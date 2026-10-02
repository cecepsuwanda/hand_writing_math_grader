"""Capability registry — normalize adapters selectable by TopicPack."""

from __future__ import annotations

from collections.abc import Sequence

from app.functions.abs_normalize import rewrite_abs_notation
from app.functions.derivative_normalize import rewrite_derivative_notation
from app.functions.det_inverse_normalize import rewrite_det_inverse_notation
from app.functions.indexed_roots_normalize import rewrite_indexed_roots
from app.functions.integral_normalize import rewrite_integral_notation
from app.functions.interval_normalize import rewrite_interval_membership
from app.functions.limit_normalize import rewrite_limit_notation
from app.functions.matrix_normalize import rewrite_matrix_notation
from app.functions.transcendental_normalize import rewrite_transcendental_notation
from app.functions.vector_normalize import rewrite_vector_notation
from app.interfaces.capability import Capability, NormalizeFn


class _FnCapability:
    def __init__(self, capability_id: str, normalize_fn: NormalizeFn) -> None:
        self._id = capability_id
        self._normalize = normalize_fn

    @property
    def id(self) -> str:
        return self._id

    def normalize(self, text: str) -> str:
        return self._normalize(text)


# Deterministic order matching legacy ``math_normalize`` pipeline.
_CAPABILITIES: dict[str, Capability] = {
    "matrix": _FnCapability("matrix", rewrite_matrix_notation),
    "det_inverse": _FnCapability("det_inverse", rewrite_det_inverse_notation),
    "vector": _FnCapability("vector", rewrite_vector_notation),
    "abs": _FnCapability("abs", rewrite_abs_notation),
    "interval": _FnCapability("interval", rewrite_interval_membership),
    "limit": _FnCapability("limit", rewrite_limit_notation),
    "derivative": _FnCapability("derivative", rewrite_derivative_notation),
    "integral": _FnCapability("integral", rewrite_integral_notation),
    "transcendental": _FnCapability(
        "transcendental", rewrite_transcendental_notation
    ),
    "indexed_roots": _FnCapability("indexed_roots", rewrite_indexed_roots),
}

# Legacy chain used without an active pack. ``indexed_roots`` is opt-in per
# pack: in other topics ``x_0`` is a point (``\lim_{x \to x_0}``), not ``x``.
ALL_CAPABILITY_IDS: tuple[str, ...] = (
    "matrix",
    "det_inverse",
    "vector",
    "abs",
    "interval",
    "limit",
    "derivative",
    "integral",
    "transcendental",
)


def apply_capabilities(text: str, capability_ids: Sequence[str]) -> str:
    """Run normalize adapters in ``capability_ids`` order (skip unknown ids)."""
    cleaned = text
    for cid in capability_ids:
        cap = _CAPABILITIES.get(cid)
        if cap is not None:
            cleaned = cap.normalize(cleaned)
    return cleaned
