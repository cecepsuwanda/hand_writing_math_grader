"""Pure string transforms for LaTeX ``\\frac`` before brace flattening."""

from __future__ import annotations


def _extract_brace_group(text: str, start: int) -> tuple[str, int] | None:
    """Return ``(inner, index_after_closing)`` starting at ``{``; else None."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    return None


# Longer names first so ``\dfrac`` is not left as a product after ``\frac`` misses it.
_FRAC_MARKERS = ("\\dfrac", "\\tfrac", "\\cfrac", "\\frac")


def _find_frac_marker(text: str, start: int) -> tuple[int, str] | None:
    """Return the earliest frac-like command at or after ``start``."""
    best: tuple[int, str] | None = None
    for marker in _FRAC_MARKERS:
        pos = text.find(marker, start)
        if pos < 0:
            continue
        if best is None or pos < best[0] or (pos == best[0] and len(marker) > len(best[1])):
            best = (pos, marker)
    return best


def rewrite_frac_notation(text: str) -> str:
    """Rewrite ``\\frac{num}{den}`` into ``((num)/(den))`` (balanced braces).

    Also accepts ``\\dfrac``, ``\\tfrac``, and ``\\cfrac``. Nested fractions
    are rewritten inside the numerator and denominator.
    """
    result: list[str] = []
    index = 0
    while index < len(text):
        found = _find_frac_marker(text, index)
        if found is None:
            result.append(text[index:])
            break
        pos, marker = found
        result.append(text[index:pos])
        cursor = pos + len(marker)
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        num = _extract_brace_group(text, cursor)
        if num is None:
            result.append(text[pos:cursor])
            index = cursor
            continue
        num_inner, after_num = num
        cursor = after_num
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        den = _extract_brace_group(text, cursor)
        if den is None:
            result.append(text[pos:after_num])
            index = after_num
            continue
        den_inner, after_den = den
        num_rewritten = rewrite_frac_notation(num_inner)
        den_rewritten = rewrite_frac_notation(den_inner)
        result.append(f"(({num_rewritten})/({den_rewritten}))")
        index = after_den
    return "".join(result)
