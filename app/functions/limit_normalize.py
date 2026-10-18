"""Pure string transforms for limit notation before SymPy parse."""

from __future__ import annotations

import re

# \lim_{x \to a}   optional signed point (-1, -\infty); optional a^+ / a^{-} / a-
_LIM_LATEX_HEAD_RE = re.compile(
    r"\\lim\s*_\s*\{\s*"
    r"(?P<var>[a-zA-Z_]\w*)\s*(?:\\to|->|→)\s*"
    r"(?P<point>[+\-]?\s*[^{}^+\-]+?)"
    r"(?P<side>\^\s*\{?\s*[+\-]\s*\}?|[+\-])?\s*\}",
    re.IGNORECASE,
)

# lim x->a expr
_LIM_ASCII_HEAD_RE = re.compile(
    r"(?<![A-Za-z\\])lim\s+"
    r"(?P<var>[a-zA-Z_]\w*)\s*(?:->|→|\\to)\s*"
    r"(?P<point>[+\-]?[^\s+\-]+?)(?P<side>[+\-])?\s+",
    re.IGNORECASE,
)

# ``L = \lim ...`` — the name is dropped; the LIMIT token is the value.
_ASSIGN_PREFIX_RE = re.compile(r"^\s*[A-Za-z]\w*\s*=\s*(?=\\?lim(?![A-Za-z]))", re.IGNORECASE)

# Where a limit body ends (outside brackets): a relation, a column / row break,
# a separator, prose, or the ``\right`` of an enclosing ``\left( ... \right)``.
_BODY_STOP_RE = re.compile(
    r"=|<|>|&|,|;|\\\\"
    r"|\\(?:le|ge|leq|geq|neq|ne|approx|to|implies|Rightarrow|quad|qquad|text|right)(?![A-Za-z])"
)

_OPENERS = "([{"
_CLOSERS = ")]}"


def _normalize_side(side: str | None) -> str:
    if not side:
        return "+-"
    cleaned = re.sub(r"[\^{}\s]", "", side)
    if cleaned.startswith("+"):
        return "+"
    if cleaned.startswith("-"):
        return "-"
    return "+-"


def _body_end(text: str, start: int) -> int:
    """Index where the limit body starting at ``start`` ends."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char in _OPENERS:
            depth += 1
        elif char in _CLOSERS:
            if depth == 0:
                return index
            depth -= 1
        elif depth == 0 and _BODY_STOP_RE.match(text, index):
            return index
        elif char == "\\" and index + 1 < len(text):
            # Skip escaped / command characters so ``\{`` or ``\,`` never close a body.
            index += 1 if text[index + 1].isalpha() else 2
            continue
        index += 1
    return len(text)


def _rewrite_heads(text: str, head_re: re.Pattern[str]) -> str:
    out: list[str] = []
    position = 0
    while True:
        match = head_re.search(text, position)
        if match is None:
            break
        end = _body_end(text, match.end())
        body = text[match.end() : end].strip()
        if not body:
            out.append(text[position : match.end()])
            position = match.end()
            continue
        var = match.group("var").strip()
        point = re.sub(r"\s+", "", match.group("point"))
        direction = _normalize_side(match.group("side"))
        before = text[position : match.start()]
        # ``\displaystyle\lim``: keep the token apart from the preceding command name.
        out.append(f"{before} " if before[-1:].isalpha() else before)
        out.append(f"LIMIT({_rewrite_heads(body, head_re)}, {var}, {point}, {direction})")
        trailing = text[match.end() : end]
        out.append(trailing[len(trailing.rstrip()) :])
        position = end
    out.append(text[position:])
    return "".join(out)


def rewrite_limit_notation(text: str) -> str:
    """Rewrite lim forms into ``LIMIT(expr, var, point, dir)`` tokens.

    The body runs to the first relation / separator outside brackets, so
    ``\\lim_{x \\to 1} (x + 1) = 2`` becomes ``LIMIT((x + 1), x, 1, +-) = 2``
    and every ``\\lim`` in a chain gets its own token.
    """
    cleaned = _ASSIGN_PREFIX_RE.sub("", text.strip())
    cleaned = _rewrite_heads(cleaned, _LIM_LATEX_HEAD_RE)
    if "LIMIT(" not in cleaned:
        cleaned = _rewrite_heads(cleaned, _LIM_ASCII_HEAD_RE)
    return cleaned
