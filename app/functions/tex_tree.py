"""Balanced LaTeX environment scanning (pure FP, no regex nesting guesses)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(
    r"\\(?P<kind>begin|end)\s*\{\s*(?P<name>[^{}\s]+)\s*\}"
    r"|(?P<item>\\item(?![A-Za-z]))"
)

_WRAPPER_RE = re.compile(r"^\\(?:textbf|textit|emph|underline)\s*\{")

_NEWCOMMAND_RE = re.compile(
    r"\\(?:re)?newcommand\s*\{?\s*\\(?P<name>[A-Za-z]+)\s*\}?\s*\[\s*1\s*\]\s*\{"
)
_TEXTCOLOR_RE = re.compile(r"\\textcolor\s*\{[^{}]*\}\s*\{")
_COLOR_RE = re.compile(r"\\color\s*\{[^{}]*\}")
_MAX_EXPANSIONS = 10_000


@dataclass(frozen=True)
class EnvSpan:
    """``tex[start:end]`` is the whole environment; ``body`` excludes begin/end."""

    name: str
    start: int
    body_start: int
    body_end: int
    end: int


def _tokens(tex: str, start: int = 0):
    return _TOKEN_RE.finditer(tex, start)


def find_environment(tex: str, name: str, start: int = 0) -> EnvSpan | None:
    """First ``\\begin{name}`` at/after ``start`` with its matching ``\\end``."""
    depth = 0
    open_match: re.Match[str] | None = None
    for match in _tokens(tex, start):
        if match.group("item") is not None or match.group("name") != name:
            continue
        if match.group("kind") == "begin":
            if depth == 0:
                open_match = match
            depth += 1
        elif depth > 0:
            depth -= 1
            if depth == 0 and open_match is not None:
                return EnvSpan(
                    name=name,
                    start=open_match.start(),
                    body_start=open_match.end(),
                    body_end=match.start(),
                    end=match.end(),
                )
    return None


def environment_body(tex: str, name: str, start: int = 0) -> str | None:
    span = find_environment(tex, name, start)
    if span is None:
        return None
    return tex[span.body_start : span.body_end]


def top_level_environments(tex: str) -> list[EnvSpan]:
    """Environments at nesting depth 0 of ``tex`` (in order)."""
    spans: list[EnvSpan] = []
    stack: list[re.Match[str]] = []
    for match in _tokens(tex):
        if match.group("item") is not None:
            continue
        if match.group("kind") == "begin":
            stack.append(match)
            continue
        if not stack:
            continue
        opened = stack.pop()
        if not stack:
            spans.append(
                EnvSpan(
                    name=opened.group("name"),
                    start=opened.start(),
                    body_start=opened.end(),
                    body_end=match.start(),
                    end=match.end(),
                )
            )
    return spans


def top_level_items(body: str) -> list[str]:
    """Split a list body on ``\\item`` tokens that are not inside a nested env."""
    depth = 0
    starts: list[int] = []
    for match in _tokens(body):
        if match.group("item") is not None:
            if depth == 0:
                starts.append(match.start())
            continue
        if match.group("kind") == "begin":
            depth += 1
        elif depth > 0:
            depth -= 1
    items: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(body)
        items.append(body[start:end])
    return items


def remove_environments(tex: str, names: frozenset[str] | set[str]) -> str:
    """Drop every top-level environment whose name is in ``names``."""
    pieces: list[str] = []
    cursor = 0
    for span in top_level_environments(tex):
        if span.name not in names:
            continue
        pieces.append(tex[cursor : span.start])
        cursor = span.end
    pieces.append(tex[cursor:])
    return "".join(pieces)


def matching_brace(text: str, open_index: int) -> int | None:
    """Index of the ``}`` closing the ``{`` at ``open_index`` (``\\{`` ignored)."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def one_arg_macros(tex: str) -> dict[str, str]:
    """``\\newcommand{\\dg}[1]{BODY}`` definitions → ``{"dg": "BODY"}``."""
    macros: dict[str, str] = {}
    for match in _NEWCOMMAND_RE.finditer(tex):
        close = matching_brace(tex, match.end() - 1)
        if close is None:
            continue
        body = tex[match.end() : close]
        if "#1" in body:
            macros[match.group("name")] = body
    return macros


def _replace_command_args(tex: str, head_re: re.Pattern[str], render) -> str:
    """Replace ``<head>{arg}`` (``head_re`` ends at the ``{``) with ``render(arg)``."""
    current = tex
    search_from = 0
    for _ in range(_MAX_EXPANSIONS):
        match = head_re.search(current, search_from)
        if match is None:
            return current
        close = matching_brace(current, match.end() - 1)
        if close is None:
            search_from = match.end()
            continue
        arg = current[match.end() : close]
        replacement = render(arg)
        current = current[: match.start()] + replacement + current[close + 1 :]
        search_from = match.start()
    return current


def expand_one_arg_macros(tex: str) -> str:
    """Inline user ``\\newcommand`` one-argument macros used in the document body."""
    for name, body in one_arg_macros(tex).items():
        usage = re.compile(rf"\\{name}(?![A-Za-z])\s*\{{")
        tex = _replace_command_args(tex, usage, lambda arg, body=body: body.replace("#1", arg))
    return tex


def strip_color_commands(tex: str) -> str:
    """``\\textcolor{Red}{23}`` → ``23``; ``\\color{Red}`` dropped."""
    tex = _replace_command_args(tex, _TEXTCOLOR_RE, lambda arg: arg)
    return _COLOR_RE.sub("", tex)


def unwrap_text_commands(text: str) -> str:
    """``\\textbf{Langkah 1: X} rest`` → ``Langkah 1: X rest`` (repeated, leading only)."""
    current = text.strip()
    while True:
        match = _WRAPPER_RE.match(current)
        if match is None:
            return current
        close = matching_brace(current, match.end() - 1)
        if close is None:
            return current
        inner = current[match.end() : close].strip()
        rest = current[close + 1 :].strip()
        current = f"{inner} {rest}".strip()
