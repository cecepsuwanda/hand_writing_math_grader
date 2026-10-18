"""Pure string transforms for ln / log / exp / e^x before SymPy parse."""

from __future__ import annotations

import re

# \ln{x}, \ln(x), \ln x  (and same for log / exp)
# A bare argument followed by ``(`` is a call (``\ln Abs(u)``), not the argument itself.
_LN_CMD_RE = re.compile(
    r"\\(?:ln|log)\b\s*(?:\{\s*(?P<braced>[^}]*)\s*\}|\(\s*(?P<paren>[^)]*)\s*\)|(?P<bare>(?:[A-Za-z_]\w*|\d+)(?![\w(])))?",
    re.IGNORECASE,
)
_EXP_CMD_RE = re.compile(
    r"\\exp\b\s*(?:\{\s*(?P<braced>[^}]*)\s*\}|\(\s*(?P<paren>[^)]*)\s*\)|(?P<bare>(?:[A-Za-z_]\w*|\d+)(?![\w(])))?",
    re.IGNORECASE,
)

# e^{...} or e^x / e^(...)
_E_POW_BRACE_RE = re.compile(r"(?<![A-Za-z0-9_])e\s*\^\s*\{\s*(?P<exp>[^}]*)\s*\}", re.IGNORECASE)
_E_POW_PAREN_RE = re.compile(r"(?<![A-Za-z0-9_])e\s*\^\s*\(\s*(?P<exp>[^)]*)\s*\)", re.IGNORECASE)
_E_POW_SIMPLE_RE = re.compile(
    r"(?<![A-Za-z0-9_])e\s*\^\s*(?P<exp>[A-Za-z_]\w*|\d+)",
    re.IGNORECASE,
)


_TRIG = r"(?:sin|cos|tan|sec|csc|cot)"
_TRIG_ARG = (
    r"(?P<arg>\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)"
    r"|\d*(?:\.\d+)?[A-Za-z](?![A-Za-z(^])"
    r"|\d+(?:\.\d+)?(?![\w(^.]))"
)
# cos^2 x → (cos(x))^2 ; cos^(3)(4x - 1) → (cos(4x - 1))^(3)
_TRIG_POWER_RE = re.compile(
    rf"(?<![A-Za-z])(?P<fn>{_TRIG})\s*\^\s*(?P<pow>\d+|\(\s*-?\d+\s*\))\s*{_TRIG_ARG}"
)
# sin x → sin(x) ; sec x tan x → sec(x) tan(x) (else SymPy reads sec(x*tan(x)))
_TRIG_BARE_ARG_RE = re.compile(rf"(?<![A-Za-z])(?P<fn>{_TRIG})\s+{_TRIG_ARG}")


def _paren(arg: str) -> str:
    return arg if arg.startswith("(") else f"({arg})"


def rewrite_trig_application(text: str) -> str:
    """Bracket bare trig arguments and move ``fn^n`` powers after the call (normalized text)."""
    cleaned = _TRIG_POWER_RE.sub(
        lambda m: f"({m.group('fn')}{_paren(m.group('arg'))})^{m.group('pow')}", text
    )
    return _TRIG_BARE_ARG_RE.sub(lambda m: f"{m.group('fn')}{_paren(m.group('arg'))}", cleaned)


def _wrap_ln(match: re.Match[str]) -> str:
    body = match.group("braced") or match.group("paren") or match.group("bare")
    if body is None:
        return "ln "
    return f"ln({body.strip()})"


def _wrap_exp(match: re.Match[str]) -> str:
    body = match.group("braced") or match.group("paren") or match.group("bare")
    if body is None:
        return "exp "
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
