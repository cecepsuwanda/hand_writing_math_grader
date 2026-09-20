"""Pure string transforms for ln / log / exp / e^x before SymPy parse."""

from __future__ import annotations

import re

# \ln{x}, \ln(x), \ln x  (and same for log / exp)
_LN_CMD_RE = re.compile(
    r"\\(?:ln|log)\b\s*(?:\{\s*(?P<braced>[^}]*)\s*\}|\(\s*(?P<paren>[^)]*)\s*\)|(?P<bare>[A-Za-z_]\w*|\d+))?",
    re.IGNORECASE,
)
_EXP_CMD_RE = re.compile(
    r"\\exp\b\s*(?:\{\s*(?P<braced>[^}]*)\s*\}|\(\s*(?P<paren>[^)]*)\s*\)|(?P<bare>[A-Za-z_]\w*|\d+))?",
    re.IGNORECASE,
)

# e^{...} or e^x / e^(...)
_E_POW_BRACE_RE = re.compile(r"(?<![A-Za-z0-9_])e\s*\^\s*\{\s*(?P<exp>[^}]*)\s*\}", re.IGNORECASE)
_E_POW_PAREN_RE = re.compile(r"(?<![A-Za-z0-9_])e\s*\^\s*\(\s*(?P<exp>[^)]*)\s*\)", re.IGNORECASE)
_E_POW_SIMPLE_RE = re.compile(
    r"(?<![A-Za-z0-9_])e\s*\^\s*(?P<exp>[A-Za-z_]\w*|\d+)",
    re.IGNORECASE,
)


def _wrap_ln(match: re.Match[str]) -> str:
    body = match.group("braced") or match.group("paren") or match.group("bare")
    if body is None:
        return "ln"
    return f"ln({body.strip()})"


def _wrap_exp(match: re.Match[str]) -> str:
    body = match.group("braced") or match.group("paren") or match.group("bare")
    if body is None:
        return "exp"
    return f"exp({body.strip()})"


def rewrite_transcendental_notation(text: str) -> str:
    """Rewrite ln/log/exp/e^ forms into parse-friendly ``ln(...)`` / ``exp(...)``."""
    cleaned = text.strip()
    cleaned = _LN_CMD_RE.sub(_wrap_ln, cleaned)
    cleaned = _EXP_CMD_RE.sub(_wrap_exp, cleaned)
    cleaned = _E_POW_BRACE_RE.sub(lambda m: f"exp({m.group('exp').strip()})", cleaned)
    cleaned = _E_POW_PAREN_RE.sub(lambda m: f"exp({m.group('exp').strip()})", cleaned)
    cleaned = _E_POW_SIMPLE_RE.sub(lambda m: f"exp({m.group('exp').strip()})", cleaned)
    return cleaned
