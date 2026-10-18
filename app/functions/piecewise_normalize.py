"""Rewrite LaTeX ``cases`` / LLM pseudo-if piecewise into SymPy ``Piecewise``."""

from __future__ import annotations

import re

from app.functions.tex_tree import find_environment

_LE_RE = re.compile(r"\\(?:leqslant|leq|le)(?![A-Za-z])|≤|⩽")
_GE_RE = re.compile(r"\\(?:geqslant|geq|ge)(?![A-Za-z])|≥|⩾")
_NE_RE = re.compile(r"\\(?:neq|ne)(?![A-Za-z])|≠")
_INF_RE = re.compile(r"\\infty\b|∞")
# ``{a if c, b if d, …}`` or bare ``a if c, b if d`` (LLM pseudo-Piecewise).
_PSEUDO_BRACE_RE = re.compile(
    r"\{(?P<body>[^{}]*\bif\b[^{}]*)\}",
    re.IGNORECASE | re.DOTALL,
)
_PSEUDO_IF_PART_RE = re.compile(
    r"^(?P<expr>.+?)\s+\bif\b\s+(?P<cond>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_CHAIN_INEQ_RE = re.compile(
    r"(?P<a>[^\s<>=!]+)\s*(?P<op1><=|>=|<|>)\s*(?P<mid>[A-Za-z]\w*)\s*"
    r"(?P<op2><=|>=|<|>)\s*(?P<b>[^\s<>=!]+)"
)
_ALREADY_PIECEWISE_RE = re.compile(r"\bPiecewise\s*\(", re.IGNORECASE)
_PIECEWISE_START_RE = re.compile(r"\bPiecewise\s*\(", re.IGNORECASE)
_STASH_MARK = "«PW{0}»"


def stash_piecewise_tokens(text: str) -> tuple[str, list[str]]:
    """Replace balanced ``Piecewise(...)`` with placeholders (opaque to other rewrites)."""
    tokens: list[str] = []
    out = text or ""
    while True:
        match = _PIECEWISE_START_RE.search(out)
        if match is None:
            break
        start = match.start()
        depth = 0
        end = None
        for index in range(match.end() - 1, len(out)):
            char = out[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            break
        tokens.append(out[start:end])
        out = out[:start] + _STASH_MARK.format(len(tokens) - 1) + out[end:]
    return out, tokens


def restore_piecewise_tokens(text: str, tokens: list[str]) -> str:
    """Undo :func:`stash_piecewise_tokens`."""
    out = text or ""
    for index, token in enumerate(tokens):
        out = out.replace(_STASH_MARK.format(index), token)
    return out


def rewrite_piecewise_notation(text: str) -> str:
    """``\\begin{cases}`` and ``{a if c, …}`` → ``Piecewise((expr, cond), …)``."""
    cleaned = text or ""
    cleaned = _rewrite_all_cases_envs(cleaned)
    cleaned = _rewrite_pseudo_if_piecewise(cleaned)
    return cleaned


def rewrite_piecewise_cases(text: str) -> str:
    """Alias used by tests / callers that only care about LaTeX cases."""
    return _rewrite_all_cases_envs(text or "")


def rewrite_pseudo_if_piecewise(text: str) -> str:
    """Alias for LLM ``{… if …}`` rewrite."""
    return _rewrite_pseudo_if_piecewise(text or "")


def _rewrite_all_cases_envs(text: str) -> str:
    out = text
    # Replace from the end so earlier spans stay valid.
    spans: list[tuple[int, int, str]] = []
    start = 0
    while True:
        span = find_environment(out, "cases", start)
        if span is None:
            break
        token = _cases_body_to_piecewise(out[span.body_start : span.body_end])
        spans.append((span.start, span.end, token))
        start = span.end
    for begin, end, token in reversed(spans):
        out = out[:begin] + token + out[end:]
    return out


def _cases_body_to_piecewise(body: str) -> str:
    branches: list[tuple[str, str]] = []
    cleaned = body.replace("\n", " ").strip()
    for raw_row in re.split(r"\\\\", cleaned):
        row = raw_row.strip().rstrip("\\").strip()
        if not row:
            continue
        # ``expr, & cond`` or ``expr & cond``
        if "&" in row:
            left, right = row.split("&", 1)
            expr = _normalize_math_atom(_strip_trailing_comma(left))
            cond = _normalize_condition(_normalize_math_atom(right.strip()))
        else:
            # ``expr, cond`` without &
            if "," in row:
                left, right = row.rsplit(",", 1)
                expr = _normalize_math_atom(_strip_trailing_comma(left))
                cond = _normalize_condition(_normalize_math_atom(right.strip()))
            else:
                continue
        if expr and cond:
            branches.append((expr, cond))
    return _format_piecewise(branches)


def _rewrite_pseudo_if_piecewise(text: str) -> str:
    if _ALREADY_PIECEWISE_RE.search(text):
        # Still rewrite remaining braced pseudo forms outside existing tokens.
        pass

    def braced(match: re.Match[str]) -> str:
        body = match.group("body")
        branches = _parse_pseudo_if_body(body)
        if not branches:
            return match.group(0)
        return _format_piecewise(branches)

    out = _PSEUDO_BRACE_RE.sub(braced, text)
    # Bare ``a if c, b if d`` without braces (whole-string heuristic).
    if " if " in out.lower() and "Piecewise(" not in out:
        branches = _parse_pseudo_if_body(out)
        if len(branches) >= 2:
            # Only replace when the whole string is pseudo-if branches.
            rebuilt = _format_piecewise(branches)
            # Preserve leading ``f(x) = `` if present.
            assign = re.match(
                r"^(?P<lhs>[^=]{1,40}=)\s*(?P<rhs>.+)$",
                out,
                re.DOTALL,
            )
            if assign is not None:
                rhs_branches = _parse_pseudo_if_body(assign.group("rhs"))
                if len(rhs_branches) >= 2:
                    return assign.group("lhs").rstrip() + " " + _format_piecewise(
                        rhs_branches
                    )
            return rebuilt
    return out


def _parse_pseudo_if_body(body: str) -> list[tuple[str, str]]:
    branches: list[tuple[str, str]] = []
    blob = body.strip().strip("{}")
    for part in re.split(r"\s*,\s*", blob):
        part = part.strip()
        if not part:
            continue
        match = _PSEUDO_IF_PART_RE.match(part)
        if match is None:
            continue
        expr = _normalize_math_atom(match.group("expr").strip())
        cond = _normalize_condition(_normalize_math_atom(match.group("cond").strip()))
        if expr and cond:
            branches.append((expr, cond))
    return branches


def _format_piecewise(branches: list[tuple[str, str]]) -> str:
    if not branches:
        return "Piecewise()"
    parts = ",".join(f"({expr}, {cond})" for expr, cond in branches)
    return f"Piecewise({parts})"


def _strip_trailing_comma(text: str) -> str:
    return re.sub(r",\s*$", "", (text or "").strip())


def _normalize_math_atom(text: str) -> str:
    cleaned = _strip_trailing_comma(text or "")
    cleaned = _LE_RE.sub("<=", cleaned)
    cleaned = _GE_RE.sub(">=", cleaned)
    cleaned = _NE_RE.sub("!=", cleaned)
    cleaned = _INF_RE.sub("oo", cleaned)
    cleaned = cleaned.replace(r"\lt", "<").replace(r"\gt", ">")
    cleaned = re.sub(r"\^\{([^{}]+)\}", r"**(\1)", cleaned)
    cleaned = re.sub(r"\^(\w)", r"**\1", cleaned)
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    return " ".join(cleaned.split())


def _normalize_condition(cond: str) -> str:
    """``-1 <= x < 2`` → ``And(-1 <= x, x < 2)`` (avoid ``&``, stripped later)."""
    cleaned = " ".join((cond or "").split())
    match = _CHAIN_INEQ_RE.fullmatch(cleaned)
    if match is not None:
        a, op1, mid, op2, b = (
            match.group("a"),
            match.group("op1"),
            match.group("mid"),
            match.group("op2"),
            match.group("b"),
        )
        return f"And({a} {op1} {mid}, {mid} {op2} {b})"
    return cleaned
