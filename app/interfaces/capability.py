"""Math capability contract — shared normalize/check adapters."""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

NormalizeFn = Callable[[str], str]


@runtime_checkable
class Capability(Protocol):
    """One claim-type adapter (interval, limit, matrix, …)."""

    @property
    def id(self) -> str:
        """Stable capability id."""

    def normalize(self, text: str) -> str:
        """Rewrite domain-specific notation toward SymPy-friendly text."""
