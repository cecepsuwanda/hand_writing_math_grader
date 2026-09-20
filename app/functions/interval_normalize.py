"""Pure string transforms for interval / membership notation."""

from __future__ import annotations

import re

# x \in (a,b) / [a,b] / (a,b] / [a,b)  and unicode ∈
_IN_INTERVAL_RE = re.compile(
    r"(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\\in|∈)\s*"
    r"(?P<left>[\[(])\s*(?P<a>[^,]+?)\s*,\s*(?P<b>[^)\]]+?)\s*(?P<right>[\])])",
    re.IGNORECASE,
)


def rewrite_interval_membership(text: str) -> str:
    """Rewrite ``x \\in (a,b)``-style membership into compound inequalities."""

    def _repl(match: re.Match[str]) -> str:
        var = match.group("var").strip()
        a = match.group("a").strip()
        b = match.group("b").strip()
        left = match.group("left")
        right = match.group("right")
        left_op = "<=" if left == "[" else "<"
        right_op = "<=" if right == "]" else "<"
        return f"{a} {left_op} {var} {right_op} {b}"

    return _IN_INTERVAL_RE.sub(_repl, text)
