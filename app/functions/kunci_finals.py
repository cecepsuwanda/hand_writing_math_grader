"""Final-answer extraction from kunci TeX (pure FP).

Explicit ``% final: <latex>`` markers win; packs pick a fallback extractor
(``HP`` for inequality packs, the last ``Jadi … $…$`` conclusion otherwise).
"""

from __future__ import annotations

import re

_FINAL_MARKER_RE = re.compile(
    r"^[ \t]*%[ \t]*final[ \t]*:[ \t]*(?P<latex>\S.*?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

_HP_COLON_RE = re.compile(
    r"HP:\s*\$(?P<hp>.+?)\$",
    re.IGNORECASE | re.DOTALL,
)
_HP_TEXT_RE = re.compile(
    r"\\text\s*\{\s*HP\s*\}\s*=\s*(?P<hp>.+?)\$",
    re.DOTALL,
)

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
_CONCLUSION_RE = re.compile(
    r"\b(?:Jadi|Sehingga|Maka|Diperoleh)\b[^$]{0,80}?\$(?P<math>[^$]+)\$",
    re.IGNORECASE,
)
_DISPLAY_LEAD_RE = re.compile(r"^\s*\\(?:displaystyle|textstyle)\s*")
_TEXT_CMD_RE = re.compile(
    r"\\text\s*\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}",
    re.IGNORECASE,
)
_EXISTENCE_RE = re.compile(
    r"^\s*(?P<neg>tidak\s+)?ada\s*$",
    re.IGNORECASE,
)


def _squash(text: str) -> str:
    return " ".join(text.split())


def canonicalize_existence_final(text: str) -> str | None:
    """Map ``\\text{ada}`` / ``tidak ada`` / ``ada`` → ``ada`` | ``tidak ada``.

    Returns ``None`` when ``text`` is not a pure existence claim (so SymPy
    compare can still try for math finals).
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # Join multi-claim finals: only accept when every segment is existence.
    parts = [p.strip() for p in re.split(r"\s*;\s*", raw) if p.strip()]
    if not parts:
        return None
    canonical: list[str] = []
    for part in parts:
        unwrapped = _TEXT_CMD_RE.sub(lambda m: m.group("body"), part)
        unwrapped = re.sub(r"\$+", "", unwrapped)
        unwrapped = _squash(unwrapped).lower()
        match = _EXISTENCE_RE.match(unwrapped)
        if match is None:
            return None
        canonical.append("tidak ada" if match.group("neg") else "ada")
    if len(set(canonical)) != 1:
        return None
    return canonical[0]


def extract_marked_finals(tex: str) -> list[str]:
    """Every ``% final: <latex>`` marker in ``tex`` (document order)."""
    return [
        _squash(match.group("latex"))
        for match in _FINAL_MARKER_RE.finditer(tex)
        if match.group("latex").strip()
    ]


def join_finals(finals: list[str]) -> str:
    """Several final answers of one soal → one ``final`` string."""
    return " ; ".join(final for final in finals if final.strip())


def _last_rhs(text: str) -> str:
    return text.rsplit("=", 1)[-1] if "=" in text else text


def extract_hp_final(tex: str) -> str | None:
    """Return HP math from ``HP: $...$`` or ``$\\text{HP} = ...$``, or None.

    A chain ``\\text{HP} = A \\cap B = C`` yields its last right-hand side ``C``.
    """
    candidates: list[tuple[int, str]] = []
    colon = _HP_COLON_RE.search(tex)
    if colon is not None:
        candidates.append((colon.start(), colon.group("hp")))
    text_form = _HP_TEXT_RE.search(tex)
    if text_form is not None:
        candidates.append((text_form.start(), _last_rhs(text_form.group("hp"))))
    if not candidates:
        return None
    return _squash(min(candidates)[1]) or None


def extract_conclusion_final(tex: str) -> str | None:
    """Math of the last ``Jadi / Sehingga / Maka … $…$`` sentence, or None."""
    matches = list(_CONCLUSION_RE.finditer(_COMMENT_RE.sub("", tex)))
    if not matches:
        return None
    math = _DISPLAY_LEAD_RE.sub("", matches[-1].group("math"))
    return _squash(math) or None


def extract_conclusion_value(tex: str) -> str | None:
    """Last right-hand side of the conclusion (``Jadi $\\lim … = 3$`` → ``3``), or None."""
    conclusion = extract_conclusion_final(tex)
    if conclusion is None:
        return None
    return _squash(_last_rhs(conclusion)) or None
