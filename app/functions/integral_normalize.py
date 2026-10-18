"""Pure string transforms for integral notation before SymPy parse."""

from __future__ import annotations

import re

# int_a^b expr dx
_INT_DEFINITE_ASCII_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?int\s*_\s*(?P<lower>[^\s^]+)\s*"
    r"\^\s*(?P<upper>\S+)\s+"
    r"(?P<expr>.+?)\s+d(?P<var>[a-zA-Z_]\w*)\s*$",
    re.IGNORECASE | re.DOTALL,
)

# int expr dx
_INT_INDEFINITE_ASCII_RE = re.compile(
    r"(?:(?P<assign>[A-Za-z]\w*)\s*=\s*)?int\s+"
    r"(?P<expr>.+?)\s+d(?P<var>[a-zA-Z_]\w*)\s*$",
    re.IGNORECASE | re.DOTALL,
)

_INT_CMD_RE = re.compile(r"\\int(?![A-Za-z])(?:\s*\\limits(?![A-Za-z]))?")
# Whole-step ``L = \int ...`` keeps the integral as the step.
_ASSIGN_PREFIX_RE = re.compile(r"^\s*[A-Za-z]\w*\s*=\s*(?=\\int(?![A-Za-z]))")
_BOUND_TOKEN_RE = re.compile(r"\s*(-?\d+(?:\.\d+)?|-?\\infty(?![A-Za-z])|\\pi(?![A-Za-z])|[A-Za-z])")
_DIFFERENTIAL_RE = re.compile(r"(?P<sep>(?:\\[,;:!]|\s)*)d\s*(?P<var>[A-Za-z])(?![A-Za-z])")
_SIZED_DELIM_RE = re.compile(r"\\(?:[bB]igg?[lr]?|left|right)\s*(?=[\[\]()|.])")
_OPENERS = "([{"
_CLOSERS = ")]}"


def _strip_wrapping(expr: str) -> str:
    cleaned = _SIZED_DELIM_RE.sub("", expr).strip()
    if len(cleaned) >= 2 and cleaned[0] == "(" and cleaned[-1] == ")":
        depth = 0
        for index, char in enumerate(cleaned):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(cleaned) - 1:
                    return cleaned
        return cleaned[1:-1].strip()
    if len(cleaned) >= 2 and cleaned[0] == "[" and cleaned[-1] == "]":
        return cleaned[1:-1].strip()
    return cleaned


def _brace_group(text: str, start: int) -> tuple[str, int] | None:
    """``{inner}`` at ``start`` → ``(inner, index_after)``."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    return None


def _read_bound(text: str, start: int) -> tuple[str, int] | None:
    """A sub/superscript bound: ``{...}`` or one token (``3``, ``-2``, ``x``, ``\\infty``)."""
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    group = _brace_group(text, cursor)
    if group is not None:
        return group[0].strip(), group[1]
    match = _BOUND_TOKEN_RE.match(text, cursor)
    if match is None:
        return None
    return match.group(1), match.end()


def _read_limits(text: str, start: int) -> tuple[str | None, str | None, int]:
    """Optional ``_a`` / ``^b`` in either order after ``\\int`` or ``]``."""
    lower: str | None = None
    upper: str | None = None
    cursor = start
    for _ in range(2):
        probe = cursor
        while probe < len(text) and text[probe].isspace():
            probe += 1
        if probe >= len(text) or text[probe] not in "_^":
            break
        bound = _read_bound(text, probe + 1)
        if bound is None:
            break
        if text[probe] == "_":
            lower = bound[0]
        else:
            upper = bound[0]
        cursor = bound[1]
    return lower, upper, cursor


def _find_differential(text: str, start: int) -> re.Match[str] | None:
    """First ``\\, dx`` at bracket depth 0 after ``start`` (ends the integrand)."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char in _OPENERS:
            depth += 1
        elif char in _CLOSERS:
            if depth == 0:
                return None
            depth -= 1
        elif depth == 0 and index > start:
            match = _DIFFERENTIAL_RE.match(text, index)
            if match is not None and (
                match.group("sep") or text[index - 1] in _CLOSERS
            ):
                return match
        if char == "\\":
            index += 1
            while index < len(text) and text[index].isalpha():
                index += 1
            continue
        index += 1
    return None


def _rewrite_latex_integrals(text: str) -> str:
    """Every ``\\int[_a^b] body \\, dx`` → ``INT(body, x[, a, b])``; unclosed ones stay."""
    out: list[str] = []
    cursor = 0
    while True:
        head = _INT_CMD_RE.search(text, cursor)
        if head is None:
            out.append(text[cursor:])
            return "".join(out)
        lower, upper, body_start = _read_limits(text, head.end())
        differential = _find_differential(text, body_start)
        body = text[body_start : differential.start()] if differential else ""
        if differential is None or not body.strip() or (lower is None) != (upper is None):
            out.append(text[cursor : head.end()])
            cursor = head.end()
            continue
        prefix = text[cursor : head.start()]
        out.append(prefix)
        if prefix and prefix[-1].isalpha():
            out.append(" ")
        expr = _strip_wrapping(body)
        var = differential.group("var")
        bounds = f", {lower}, {upper}" if lower is not None else ""
        out.append(f"INT({expr}, {var}{bounds})")
        cursor = differential.end()


def _bar_variable(body: str) -> str | None:
    """The one free letter of an antiderivative (``C`` / ``e`` are constants)."""
    plain = re.sub(r"\\[A-Za-z]+", " ", body)
    letters = set(re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", plain)) - {"C", "e"}
    if len(letters) == 1:
        return letters.pop()
    return "x" if "x" in letters else None


def _substitute(body: str, var: str, value: str) -> str:
    return re.sub(rf"(?<![A-Za-z\\]){var}(?![A-Za-z])", f"({value})", body)


def rewrite_evaluation_brackets(text: str) -> str:
    """``\\Bigl[F\\Bigr]_a^b`` / ``[F]_a^b`` → ``((F(b)) - (F(a)))`` (antiderivative evaluated)."""
    out: list[str] = []
    cursor = 0
    index = 0
    while index < len(text):
        if text[index] != "[":
            index += 1
            continue
        depth = 0
        close = -1
        for probe in range(index, len(text)):
            if text[probe] == "[":
                depth += 1
            elif text[probe] == "]":
                depth -= 1
                if depth == 0:
                    close = probe
                    break
        if close < 0:
            break
        lower, upper, after = _read_limits(text, close + 1)
        body = re.sub(r"\\[bB]igg?r\s*$", "", text[index + 1 : close]).strip()
        var = _bar_variable(body) if lower is not None and upper is not None else None
        if var is None:
            index += 1
            continue
        opener = re.search(r"\\[bB]igg?l\s*$", text[cursor:index])
        start = cursor + opener.start() if opener else index
        out.append(text[cursor:start])
        out.append(f"(({_substitute(body, var, upper)}) - ({_substitute(body, var, lower)}))")
        cursor = index = after
    out.append(text[cursor:])
    return "".join(out)


def rewrite_integral_notation(text: str) -> str:
    """Rewrite integral forms into ``INT(expr, var)`` or ``INT(expr, var, a, b)``."""

    def _indefinite(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        expr = _strip_wrapping(match.group("expr"))
        return f"INT({expr}, {var})"

    def _definite(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        expr = _strip_wrapping(match.group("expr"))
        lower = match.group("lower").strip()
        upper = match.group("upper").strip()
        return f"INT({expr}, {var}, {lower}, {upper})"

    cleaned = rewrite_evaluation_brackets(text.strip())
    if _INT_CMD_RE.search(cleaned):
        updated = _rewrite_latex_integrals(_ASSIGN_PREFIX_RE.sub("", cleaned))
        if "INT(" in updated:
            return updated

    if re.match(r"(?:[A-Za-z]\w*\s*=\s*)?int\s*_", cleaned, re.IGNORECASE):
        updated = _INT_DEFINITE_ASCII_RE.sub(_definite, cleaned)
        if "INT(" in updated:
            return updated
    updated = _INT_INDEFINITE_ASCII_RE.sub(_indefinite, cleaned)
    return updated
