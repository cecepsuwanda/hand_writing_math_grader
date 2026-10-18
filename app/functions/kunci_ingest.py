"""Pure helpers to ingest kunci_jawaban TeX into standards solution files."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from string import ascii_lowercase
from typing import TYPE_CHECKING

from app.functions.kunci_finals import (
    canonicalize_existence_final,
    extract_hp_final,
    extract_marked_finals,
    join_finals,
)
from app.functions.standard_extract import (
    exam_schema_path,
    extract_solution_steps_from_tex,
)
from app.functions.function_ingest import (
    enrich_milestone_steps,
    extract_marked_concepts,
    extract_marked_value_table,
    is_domain_and_range_title,
    split_domain_range_steps,
    value_table_step_payloads,
    value_table_symbolic_payload,
)
from app.functions.graph_points import (
    domain_claim_from_final,
    extract_marked_graph_points,
)
from app.functions.number_line import number_line_from_symbolic, number_line_to_repr
from app.functions.paths import list_kunci_tex, pick_topic_kunci_tex
from app.functions.symbolic_from_latex import latex_to_symbolic_payload
from app.functions.tex_tree import (
    EnvSpan,
    environment_body,
    expand_one_arg_macros,
    find_environment,
    remove_environments,
    strip_color_commands,
    top_level_environments,
    top_level_items,
    unwrap_text_commands,
)
from app.models.defaults import DEFAULT_TOPIC_ID
from app.models.recognition import SymbolicPayload
from app.models.exam_schema import (
    ExamMethod,
    ExamMilestone,
    ExamPart,
    ExamQuestion,
    ExamSchema,
)
from app.models.grading import Rubric
from app.topics.runtime import using_pack

if TYPE_CHECKING:
    from app.interfaces.topic_pack import TopicPack

__all__ = ["extract_hp_final"]

_ITEM_HEAD_RE = re.compile(r"\\item(?![A-Za-z])(?:\s*\[[^\]]*\])?\s*")

# Where the problem statement ends and the worked answer begins.
_ANSWER_START_RE = re.compile(
    r"\\textbf\s*\{\s*(?:Penyelesaian|Jawab(?:an)?)\s*:?\s*\}",
    re.IGNORECASE,
)
_STEM_STOP_RE = re.compile(
    r"\\textbf\s*\{\s*(?:Penyelesaian|Jawab)"
    r"|\\begin\s*\{\s*(?:itemize|enumerate|align\*?|aligned\*?)\s*\}",
    re.IGNORECASE,
)

_TEX_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

_QUAD_TEXT_RE = re.compile(
    r"\\quad\s*\\text\{(?:[^{}]|\{[^{}]*\})*\}",
)
# ``\text{Ekspansi: } x^2 + ...`` → keep the math after a label ending in ``:``.
_LEADING_LABEL_RE = re.compile(r"^\\text\s*\{[^{}]*:\s*\}\s*(?=\S)")

_TIKZ_RE = re.compile(r"\\begin\s*\{\s*tikzpicture\s*\}", re.IGNORECASE)
_CENTER_RE = re.compile(r"\\(?:begin|end)\s*\{\s*center\s*\}")

_SUB_LABEL_RE = re.compile(
    r"\\item\s*\[\s*\(?\s*(?P<label>[a-z]{1,4})\s*[.)]?\s*\]",
    re.IGNORECASE,
)
# ``\text{(a)}\quad u \cdot v = 0`` — an align row tagged for sub-soal (a).
_ROW_PART_LABEL_RE = re.compile(
    r"^\\text\s*\{\s*\((?P<label>[a-z]{1,4})\)\s*\}\s*(?:\\q?quad\b|\\[;,:!]|~|\s)*",
    re.IGNORECASE,
)
_STEM_NOISE_RE = re.compile(
    r"\\\\(?:\s*\[[^\]]*\])?"
    r"|\\begin\s*\{[^{}]*\}(?:\s*\{[^{}]*\})?"
    r"|\\end\s*\{[^{}]*\}"
    r"|\\q?quad\b|\\\[|\\\]|&"
)
_FRAGMENT_EDGE_RE = re.compile(r"^[}\s]+|(?:\\text\s*\{|[{\s])+$")

_LIST_ENVS = frozenset({"itemize", "enumerate"})

_METHOD_TITLE_RE = re.compile(
    r"^(?:Metode|Cara)\s+(?P<n>\d+)\s*:\s*(?P<label>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_LANGKAH_TITLE_RE = re.compile(r"^Langkah", re.IGNORECASE)
_LANGKAH_PREFIX_RE = re.compile(r"^Langkah\s+\d+\s*[:.]\s*", re.IGNORECASE)

_SOAL_MARKER_RE = re.compile(
    r"%\s*soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_GAMBAR_MARKER_RE = re.compile(
    r"%\s*gambar\s+soal\s+ke\s+(?P<n>\d+)\b",
    re.IGNORECASE,
)
_SOAL_BLOCK_SPLIT_RE = re.compile(
    r"(?=%\s*soal\s+ke\s+\d+\b)",
    re.IGNORECASE,
)

_NO_EXAM_KEY = (
    "(no exam key provided; infer question_number from handwriting if visible)"
)

_METHOD_LABEL_IDS: dict[str, str] = {
    "pemaktoran": "factoring",
    "pemfaktoran": "factoring",
    "rumus abc": "quadratic_formula",
    "abc": "quadratic_formula",
}

_NON_MILESTONE_ROLES = frozenset({"algebra", "figure", "hp"})


@dataclass(frozen=True)
class _IngestRules:
    """TopicPack ingest vocabulary, compiled once per ingest call."""

    section_roles: tuple[tuple[re.Pattern[str], str], ...]
    milestone_roles: tuple[str, ...]
    figure_from_tikz: bool
    number_line: bool
    # Pack-opt-in (function_3): derive number_line from D_f when not a graph soal.
    domain_number_line: bool
    # Pack has ``graph`` in figure_kinds — Gambar Grafik sections skip HP→number_line.
    graph_kind: bool
    # Pack-opt-in (function_3): prose + tabular + Domain/Range split.
    rich_section_ingest: bool
    extract_final: Callable[[str], str | None]


def _resolve_pack(topic_pack: TopicPack | None, topic_id: str | None) -> TopicPack:
    from app.topics.registry import get_pack, resolve_pack

    if topic_pack is not None:
        return topic_pack
    if topic_id is not None and topic_id.strip():
        return get_pack(topic_id)
    return resolve_pack()


def _rules_for(pack: TopicPack) -> _IngestRules:
    section_roles = tuple(
        (re.compile(pattern, re.IGNORECASE), role)
        for pattern, role in pack.ingest_section_roles
    )
    titled = {role for _, role in section_roles}
    milestone_roles = tuple(
        kind
        for kind in pack.part_kinds
        if kind in titled and kind not in _NON_MILESTONE_ROLES
    )
    return _IngestRules(
        section_roles=section_roles,
        milestone_roles=milestone_roles,
        figure_from_tikz=bool(pack.figure_from_tikz),
        number_line="number_line" in pack.figure_kinds,
        domain_number_line=bool(getattr(pack, "domain_number_line_from_final", False)),
        graph_kind="graph" in pack.figure_kinds,
        rich_section_ingest=bool(getattr(pack, "rich_section_ingest", False)),
        extract_final=pack.extract_final,
    )


def prepare_kunci_tex(tex: str) -> str:
    """Inline preamble one-argument macros and drop colour wrappers."""
    return strip_color_commands(expand_one_arg_macros(tex))


def extract_soal_number(item_tex: str) -> int | None:
    """Return ``N`` from ``% soal ke N`` if present."""
    match = _SOAL_MARKER_RE.search(item_tex)
    if match is None:
        return None
    return int(match.group("n"))


def item_has_gambar_marker(item_tex: str) -> bool:
    """True if ``% gambar soal ke N`` appears in the block."""
    return _GAMBAR_MARKER_RE.search(item_tex) is not None


def split_enumerate_items(tex: str) -> list[str]:
    """Return the outer enumerate's top-level ``\\item`` blocks (one per soal).

    When ``% soal ke N`` markers exist, split on those markers so each block
    keeps its soal/jawaban/gambar comments.
    """
    body = environment_body(tex, "enumerate")
    if body is None:
        return []
    if _SOAL_MARKER_RE.search(body):
        items: list[str] = []
        for chunk in _SOAL_BLOCK_SPLIT_RE.split(body):
            cleaned = chunk.strip()
            if cleaned and _SOAL_MARKER_RE.search(cleaned) and "\\item" in cleaned:
                items.append(cleaned)
        if items:
            return items

    return [
        cleaned
        for cleaned in (item.strip() for item in top_level_items(body))
        if _ITEM_HEAD_RE.sub("", cleaned, count=1).strip()
    ]


def _clean_align_steps(raw_steps: list[str]) -> list[str]:
    steps: list[str] = []
    for step in raw_steps:
        cleaned = _QUAD_TEXT_RE.sub("", step)
        cleaned = " ".join(cleaned.split())
        cleaned = _LEADING_LABEL_RE.sub("", cleaned, count=1)
        if cleaned:
            steps.append(cleaned)
    return steps


def extract_align_steps(item_tex: str) -> list[str]:
    """Extract align/aligned rows from one question block; strip ``\\quad\\text``."""
    return _clean_align_steps(extract_solution_steps_from_tex(item_tex))


def _stem_bounds(item_tex: str) -> tuple[int, int] | None:
    head = _ITEM_HEAD_RE.search(item_tex)
    if head is None:
        return None
    stop = _STEM_STOP_RE.search(item_tex, head.end())
    return head.end(), stop.start() if stop is not None else len(item_tex)


def answer_tex(item_tex: str) -> str:
    """The worked-answer part of a soal block (after ``Jawab:`` / the stem)."""
    marker = _ANSWER_START_RE.search(item_tex)
    if marker is not None:
        return item_tex[marker.end() :]
    bounds = _stem_bounds(item_tex)
    return item_tex[bounds[1] :] if bounds is not None else item_tex


@dataclass(frozen=True)
class _Section:
    title: str
    is_langkah: bool
    own: str
    children: str | None


def _strip_comment_line(line: str) -> str:
    return _TEX_COMMENT_RE.sub("", line).strip()


def _normalize_title(raw_title: str) -> tuple[str, bool]:
    """``\\textbf{Langkah 2: Tentukan Titik Kritis}`` → (``Tentukan Titik Kritis``, True)."""
    title = unwrap_text_commands(raw_title)
    is_langkah = bool(_LANGKAH_TITLE_RE.match(title))
    stripped = _LANGKAH_PREFIX_RE.sub("", title, count=1).strip()
    return (stripped or title), is_langkah


def _list_sections(list_body: str) -> list[_Section]:
    """Top-level ``\\item`` sections of one itemize/enumerate body."""
    sections: list[_Section] = []
    for chunk in top_level_items(list_body):
        head = _ITEM_HEAD_RE.match(chunk)
        content = chunk[head.end() :] if head is not None else chunk
        lines = content.splitlines()
        raw_title = ""
        body_start = 0
        for index, line in enumerate(lines):
            stripped = _strip_comment_line(line)
            if stripped:
                raw_title = stripped
                body_start = index + 1
                break
        rest = "\n".join(lines[body_start:])
        if not rest.strip():
            rest = content
        nested = next(
            (span for span in top_level_environments(rest) if span.name in _LIST_ENVS),
            None,
        )
        children = rest[nested.body_start : nested.body_end] if nested else None
        own = remove_environments(rest, _LIST_ENVS)
        title, is_langkah = _normalize_title(raw_title)
        sections.append(
            _Section(title=title, is_langkah=is_langkah, own=own, children=children)
        )
    return sections


def _method_label(label: str) -> str:
    head = re.split(r"[$,]", label, maxsplit=1)[0]
    return " ".join(head.split()).strip(" :.")


def _method_id_from_label(label: str, method_number: int) -> str:
    key = " ".join(label.lower().split())
    if key in _METHOD_LABEL_IDS:
        return _METHOD_LABEL_IDS[key]
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return slug or f"method_{method_number}"


def _symbolic_steps(steps: list[str]) -> list:
    return [latex_to_symbolic_payload(step) for step in steps]


def _milestone_symbolic(role: str, latex: str, steps: list[str]):
    if role == "value_table":
        return value_table_symbolic_payload(steps) or (
            value_table_symbolic_payload([latex]) if latex else None
        )
    return latex_to_symbolic_payload(latex) if latex else None


def _milestone_steps_symbolic(role: str, steps: list[str]) -> list:
    if role == "value_table":
        return value_table_step_payloads(steps)
    return _symbolic_steps(steps)


def _final_symbolic(final_text: str) -> SymbolicPayload | None:
    existence = canonicalize_existence_final(final_text)
    if existence is not None:
        return SymbolicPayload(kind="expression", repr=existence)
    return latex_to_symbolic_payload(final_text)


def _section_role(section: _Section, rules: _IngestRules) -> str:
    for pattern, role in rules.section_roles:
        if pattern.match(section.title):
            return role
    if rules.figure_from_tikz and _TIKZ_RE.search(section.own):
        return "figure"
    return "algebra"


@dataclass
class _MethodAcc:
    id: str
    label: str
    steps: list[str] = field(default_factory=list)


@dataclass
class _WalkAcc:
    """Mutable accumulator for one soal's answer tree (local to ``build_exam_question``)."""

    shared: list[str] = field(default_factory=list)
    methods: list[_MethodAcc] = field(default_factory=list)
    milestones: dict[str, list[str]] = field(default_factory=dict)
    milestone_titles: dict[str, str] = field(default_factory=dict)
    canonical_method: int | None = None
    saw_top_method: bool = False
    saw_figure: bool = False

    def add_method(self, label: str, number: int) -> int:
        method_id = _method_id_from_label(label, number)
        taken = {method.id for method in self.methods}
        base, suffix = method_id, 2
        while method_id in taken:
            method_id = f"{base}_{suffix}"
            suffix += 1
        self.methods.append(_MethodAcc(id=method_id, label=label))
        return len(self.methods) - 1


def _walk_sections(
    list_body: str,
    acc: _WalkAcc,
    rules: _IngestRules,
    *,
    method_index: int | None,
    role_ctx: str | None,
    depth: int,
) -> None:
    """Route align rows of every (nested) section into shared / method / milestone.

    The canonical flow is the part outside any method plus the first method
    that is a full alternative path (``Cara 1``); milestones only come from it.
    Methods nested under a milestone section (``Titik Kritis`` → ``Metode 1``)
    are alternatives for that milestone; the first one fills it.
    """
    for section in _list_sections(list_body):
        own_steps = extract_align_steps(section.own)
        method_match = _METHOD_TITLE_RE.match(section.title)
        if method_match is not None:
            label = _method_label(method_match.group("label"))
            index = acc.add_method(label, int(method_match.group("n")))
            acc.methods[index].steps.extend(own_steps)
            if depth == 0:
                acc.saw_top_method = True
            if role_ctx is None and acc.canonical_method is None:
                acc.canonical_method = index
            if role_ctx in acc.milestones and not acc.milestones[role_ctx]:
                acc.milestones[role_ctx] = list(own_steps)
            if section.children is not None:
                _walk_sections(
                    section.children,
                    acc,
                    rules,
                    method_index=index,
                    role_ctx=role_ctx,
                    depth=depth + 1,
                )
            continue

        role = _section_role(section, rules)
        if rules.rich_section_ingest:
            own_steps = enrich_milestone_steps(role, section.own, own_steps)
        canonical = method_index is None or method_index == acc.canonical_method
        is_milestone = role in rules.milestone_roles
        if role == "algebra":
            if method_index is not None:
                acc.methods[method_index].steps.extend(own_steps)
            elif not (depth == 0 and acc.saw_top_method and not section.is_langkah):
                acc.shared.extend(own_steps)
        elif role == "figure":
            acc.saw_figure = True
        elif (
            rules.rich_section_ingest
            and is_milestone
            and canonical
            and is_domain_and_range_title(section.title)
        ):
            domain_steps, range_steps = split_domain_range_steps(own_steps)
            if "domain" not in acc.milestones and domain_steps:
                acc.milestones["domain"] = domain_steps
                acc.milestone_titles["domain"] = section.title
            if "range" not in acc.milestones and range_steps:
                acc.milestones["range"] = range_steps
                acc.milestone_titles["range"] = section.title
            if "domain" not in acc.milestones and not domain_steps and own_steps:
                acc.milestones["domain"] = list(own_steps)
                acc.milestone_titles["domain"] = section.title
        elif is_milestone and canonical and role not in acc.milestones:
            acc.milestones[role] = list(own_steps)
            acc.milestone_titles[role] = section.title
        elif (
            rules.rich_section_ingest
            and is_milestone
            and canonical
            and role in acc.milestones
            and own_steps
        ):
            # Append more evidence (e.g. second concept section) without replacing.
            merged = list(acc.milestones[role])
            for step in own_steps:
                if step not in merged:
                    merged.append(step)
            acc.milestones[role] = merged

        if section.children is not None:
            _walk_sections(
                section.children,
                acc,
                rules,
                method_index=method_index,
                role_ctx=role if is_milestone else role_ctx,
                depth=depth + 1,
            )


def render_standard_solution_tex(
    steps: list[str] | None = None,
    final: str = "",
    *,
    source_note: str = "",
    question: ExamQuestion | None = None,
) -> str:
    """Build standards-format solution TeX (tagged methods + ``% final answer``)."""
    header = "% Ingested from kunci_jawaban"
    if source_note:
        header = f"{header} ({source_note})"
    lines = [header]

    if question is not None:
        shared = list(question.steps)
        if shared:
            lines.append("% shared")
            _append_aligned_block(lines, shared)
        for method in question.methods:
            lines.append(f"% method: {method.id}")
            _append_aligned_block(lines, method.steps)
        for milestone in question.milestones:
            if milestone.role == "hp":
                continue
            lines.append(f"% role: {milestone.role}")
            if milestone.steps:
                _append_aligned_block(lines, milestone.steps)
            elif (milestone.latex or "").strip():
                lines.append(f"% {milestone.latex.strip()}")
                lines.append("")
        if question.expects_figure:
            lines.append("% role: figure")
            if question.number_line is not None and question.number_line.intervals:
                lines.append(
                    f"% number_line: {number_line_to_repr(question.number_line)}"
                )
            lines.append("")
        final_text = (question.final or final or "").strip()
    else:
        shared = list(steps or [])
        if shared:
            lines.append("% shared")
            _append_aligned_block(lines, shared)
        final_text = (final or "").strip()

    lines.append("% final answer")
    lines.append(final_text)
    lines.append("")
    return "\n".join(lines)


def _append_aligned_block(lines: list[str], steps: list[str]) -> None:
    if not steps:
        return
    lines.append(r"\begin{aligned}")
    for index, step in enumerate(steps):
        suffix = r" \\" if index < len(steps) - 1 else ""
        lines.append(f"{step}{suffix}")
    lines.append(r"\end{aligned}")
    lines.append("")


def rubric_from_parts(
    question_number: int,
    parts: list[ExamPart],
    *,
    topic_id: str | None = None,
) -> Rubric:
    """Build a rubric from exam parts via the active / resolved TopicPack."""
    from app.topics.registry import resolve_pack

    return resolve_pack(topic_id=topic_id).rubric_from_parts(question_number, parts)


def extract_question_stem(item_tex: str) -> str | None:
    """Return the problem stem (text after ``\\item``), excluding the answer body.

    A question list (``\\begin{enumerate}`` of sub-questions answered by one
    shared ``Jawab``) is kept in the stem as ``(a) ... (b) ...``. When every
    sub-item carries its own ``Jawab``, only the shared lead-in is returned.
    TikZ pictures in the stem become ``[gambar]``.
    """
    head = _ITEM_HEAD_RE.search(item_tex)
    if head is None:
        return None
    sub_list = _stem_sub_list(item_tex)
    if sub_list is None:
        bounds = _stem_bounds(item_tex)
        return _clean_stem(item_tex[bounds[0] : bounds[1]]) if bounds else None
    lead = _clean_stem(item_tex[head.end() : sub_list.span.start])
    if sub_list.answered:
        return lead or None
    listed = [
        f"({label}) {_clean_stem(_ITEM_HEAD_RE.sub('', chunk, count=1))}"
        for label, chunk in sub_list.labeled_items()
    ]
    return " ".join(part for part in (lead, *listed) if part) or None


def _clean_stem(raw: str) -> str:
    text = _TEX_COMMENT_RE.sub("", raw)
    while (span := find_environment(text, "tikzpicture")) is not None:
        text = f"{text[: span.start]} [gambar] {text[span.end :]}"
    text = _CENTER_RE.sub(" ", text)
    return " ".join(text.split())


@dataclass(frozen=True)
class _SubList:
    """Top-level ``enumerate`` inside a soal's statement (before its own Jawab)."""

    span: EnvSpan
    items: tuple[str, ...]
    # True: every sub-item is answered on its own (sub-soal); False: question list.
    answered: bool

    def labeled_items(self) -> list[tuple[str, str]]:
        return [
            (_item_label(chunk) or _letter_label(index), chunk)
            for index, chunk in enumerate(self.items)
        ]


def _item_label(chunk: str) -> str | None:
    """``\\item[(a)]`` / ``\\item[a)]`` / ``\\item[a.]`` → ``"a"``; plain ``\\item`` → None."""
    match = _SUB_LABEL_RE.match(chunk.lstrip())
    return match.group("label").lower() if match is not None else None


def _letter_label(index: int) -> str:
    return ascii_lowercase[index % 26] * (index // 26 + 1)


def _own_answer_marker(item_tex: str) -> int | None:
    """Offset of the item's own ``Jawab:`` (not one nested in a sub-list)."""
    spans = top_level_environments(item_tex)
    for match in _ANSWER_START_RE.finditer(item_tex):
        if not any(span.start <= match.start() < span.end for span in spans):
            return match.start()
    return None


def _stem_sub_list(item_tex: str) -> _SubList | None:
    limit = _own_answer_marker(item_tex)
    for span in top_level_environments(item_tex):
        if limit is not None and span.start >= limit:
            return None
        if span.name != "enumerate":
            continue
        items = tuple(
            chunk.strip()
            for chunk in top_level_items(item_tex[span.body_start : span.body_end])
            if _ITEM_HEAD_RE.sub("", chunk.strip(), count=1).strip()
        )
        if not items:
            return None
        answered = any(_ANSWER_START_RE.search(chunk) for chunk in items)
        if not answered and limit is None:
            return None
        return _SubList(span=span, items=items, answered=answered)
    return None


def extract_question_stems(tex: str, *, topic_id: str | None = None) -> list[tuple[int, str]]:
    """Parse kunci TeX into ``(question_number, stem)`` pairs (1-based).

    Stems are problem statements only — never align steps or HP.
    Honors ``% soal ke N`` when present. Sub-soal repeat their number.
    """
    questions = _build_questions(tex, _resolve_pack(None, topic_id))
    return [(question.number, question.stem) for question in questions]


def load_question_stems_from_kunci(
    path_or_dir: Path | str, *, topic_id: str | None = None
) -> list[tuple[int, str]]:
    """Load stems from a kunci ``.tex`` file or from a directory.

    In a directory the only ``.tex`` is used, else ``tugas_topik_<bab>.tex`` of
    ``topic_id``; without ``topic_id`` the first ``.tex`` by name. Returns ``[]``
    if the path is missing, empty, ambiguous, or has no parseable stems.
    """
    path = Path(path_or_dir)
    if not path.exists():
        return []
    if path.is_dir():
        tex_files = list_kunci_tex(path)
        if not tex_files:
            return []
        chosen = (
            pick_topic_kunci_tex(tex_files, topic_id) if topic_id else tex_files[0]
        )
        if chosen is None:
            return []
        path = chosen
    if not path.is_file():
        return []
    try:
        tex = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return extract_question_stems(tex, topic_id=topic_id)


def item_has_tikzpicture(item_tex: str) -> bool:
    """True if the question's answer contains a TikZ picture environment."""
    return _TIKZ_RE.search(answer_tex(item_tex)) is not None


def item_expects_figure(item_tex: str) -> bool:
    """True if marker ``% gambar soal ke N`` or a tikzpicture is in the answer."""
    return item_has_gambar_marker(item_tex) or item_has_tikzpicture(item_tex)


def build_exam_question(
    number: int,
    item_tex: str,
    *,
    topic_pack: TopicPack | None = None,
) -> ExamQuestion | None:
    """Build one ``ExamQuestion`` from an enumerate item (stem required).

    ``number`` is the fallback index; ``% soal ke N`` overrides when present.
    Top-level ``steps`` are shared algebra only (pre-method). Alternate
    ``Metode N`` / ``Cara N`` blocks go into ``methods`` and are not flattened
    into steps. Section roles, figure detection and the final-answer fallback
    come from ``topic_pack`` (active / default pack when omitted); explicit
    ``% final: <latex>`` lines always win. For a soal split into sub-soal this
    is the first sub-soal; see ``build_item_questions``.
    """
    questions = build_item_questions(number, item_tex, topic_pack=topic_pack)
    return questions[0] if questions else None


def build_item_questions(
    number: int,
    item_tex: str,
    *,
    topic_pack: TopicPack | None = None,
) -> list[ExamQuestion]:
    """All ``ExamQuestion`` of one top-level item: the soal, or its sub-soal.

    Sub-soal (``part_label`` ``a``, ``b``, ...) come from a nested ``enumerate``
    whose items each have their own ``Jawab:``, or from ``\\item[(a)]`` lists
    inside the answer. Sub-soal stem = shared lead-in + the sub-question text.
    """
    pack = _resolve_pack(topic_pack, None)
    with using_pack(pack):
        return _build_item_questions(number, item_tex, _rules_for(pack))


def _build_item_questions(
    number: int,
    item_tex: str,
    rules: _IngestRules,
) -> list[ExamQuestion]:
    marked = extract_soal_number(item_tex)
    qnum = marked if marked is not None else number
    sub_list = _stem_sub_list(item_tex)
    if sub_list is not None and sub_list.answered:
        lead = extract_question_stem(item_tex) or ""
        questions: list[ExamQuestion] = []
        for label, chunk in sub_list.labeled_items():
            sub_stem = extract_question_stem(chunk)
            if sub_stem is None:
                continue
            stem = " ".join(part for part in (lead, sub_stem) if part)
            questions.append(
                _build_exam_question(qnum, chunk, rules, stem=stem, part_label=label)
            )
        return questions

    stem = extract_question_stem(item_tex)
    if stem is None:
        return []
    labeled = _labeled_answer_items(answer_tex(item_tex))
    if len({label for label, _ in labeled}) >= 2:
        return _labeled_sub_questions(qnum, stem, item_tex, labeled, rules)
    return [_build_exam_question(qnum, item_tex, rules, stem=stem)]


def _labeled_answer_items(tex: str) -> list[tuple[str, str]]:
    """``\\item[(a)]`` blocks anywhere in an answer (labelled items are not entered)."""
    found: list[tuple[str, str]] = []
    for span in top_level_environments(tex):
        body = tex[span.body_start : span.body_end]
        if span.name not in _LIST_ENVS:
            found.extend(_labeled_answer_items(body))
            continue
        for chunk in top_level_items(body):
            label = _item_label(chunk)
            if label is None:
                found.extend(_labeled_answer_items(chunk))
            else:
                found.append((label, chunk))
    return found


def _labeled_sub_questions(
    number: int,
    stem: str,
    item_tex: str,
    labeled: list[tuple[str, str]],
    rules: _IngestRules,
) -> list[ExamQuestion]:
    """One sub-soal per ``\\item[(x)]`` label; rows tagged ``\\text{(x)}`` join it."""
    tagged: dict[str, list[str]] = {}
    for row in extract_align_steps(answer_tex(item_tex)):
        match = _ROW_PART_LABEL_RE.match(row)
        if match is not None:
            tagged.setdefault(match.group("label").lower(), []).append(row[match.end() :])
    chunks: dict[str, list[str]] = {}
    for label, chunk in labeled:
        chunks.setdefault(label, []).append(chunk)

    questions: list[ExamQuestion] = []
    for label, label_chunks in chunks.items():
        body = "\n".join(label_chunks)
        steps = list(tagged.get(label, []))
        for row in extract_align_steps(body):
            row = _ROW_PART_LABEL_RE.sub("", row, count=1)
            if row and row not in steps:
                steps.append(row)
        questions.append(
            _assemble_question(
                number=number,
                part_label=label,
                stem=_labeled_sub_stem(stem, label, list(chunks)),
                acc=_WalkAcc(shared=steps),
                final_text=_question_final(body, body, rules),
                expects_figure=False,
                rules=rules,
            )
        )
    return questions


def _labeled_sub_stem(stem: str, label: str, labels: list[str]) -> str:
    """Lead-in of ``stem`` + the ``(label) ...`` segment when the stem lists them."""
    marks = {other: stem.find(f"({other})") for other in labels}
    start = marks[label]
    if start < 0:
        return f"{stem} ({label})"
    first = min(pos for pos in marks.values() if pos >= 0)
    end = min((pos for pos in marks.values() if pos > start), default=len(stem))
    lead = _tidy_fragment(stem[:first])
    segment = _tidy_fragment(stem[start + len(label) + 2 : end])
    in_display_math = stem.count(r"\[", 0, start) > stem.count(r"\]", 0, start)
    if segment and in_display_math:
        segment = f"${segment}$"
    return " ".join(part for part in (lead, f"({label})", segment) if part)


def _tidy_fragment(text: str) -> str:
    text = " ".join(_STEM_NOISE_RE.sub(" ", text).split())
    return _FRAGMENT_EDGE_RE.sub("", text)


def _build_exam_question(
    number: int,
    item_tex: str,
    rules: _IngestRules,
    *,
    stem: str,
    part_label: str = "",
) -> ExamQuestion:
    answer = answer_tex(item_tex)
    acc = _WalkAcc()
    top_list = find_environment(answer, "itemize")
    if top_list is not None:
        _walk_sections(
            answer[top_list.body_start : top_list.body_end],
            acc,
            rules,
            method_index=None,
            role_ctx=None,
            depth=0,
        )
        if not acc.methods and not acc.shared:
            acc.shared = extract_align_steps(answer)
    else:
        acc.shared = extract_align_steps(answer)

    return _assemble_question(
        number=number,
        part_label=part_label,
        stem=stem,
        acc=acc,
        final_text=_question_final(item_tex, answer, rules),
        expects_figure=(
            item_has_gambar_marker(item_tex)
            or acc.saw_figure
            or (rules.figure_from_tikz and item_has_tikzpicture(item_tex))
        ),
        rules=rules,
        item_tex=item_tex,
        saw_figure=acc.saw_figure,
    )


def _merge_marked_milestones(
    milestones: list[ExamMilestone],
    acc: _WalkAcc,
    *,
    concept_steps: list[str],
    value_table_steps: list[str],
) -> None:
    """Fold ``% concept:`` / ``% value_table:`` markers into milestones + ``acc``."""
    for role, marked in (
        ("concept", concept_steps),
        ("value_table", value_table_steps),
    ):
        if not marked:
            continue
        existing = list(acc.milestones.get(role, []))
        merged = list(existing)
        for step in marked:
            if step not in merged:
                merged.append(step)
        acc.milestones[role] = merged
        latex = " ; ".join(merged) if merged else acc.milestone_titles.get(role, "")
        payload = ExamMilestone(
            role=role,
            title=acc.milestone_titles.get(role, ""),
            latex=latex,
            symbolic=_milestone_symbolic(role, latex, merged),
            steps=merged,
            steps_symbolic=_milestone_steps_symbolic(role, merged),
        )
        replaced = False
        for index, milestone in enumerate(milestones):
            if milestone.role == role:
                milestones[index] = payload
                replaced = True
                break
        if not replaced:
            milestones.append(payload)


def _assemble_question(
    *,
    number: int,
    part_label: str,
    stem: str,
    acc: _WalkAcc,
    final_text: str,
    expects_figure: bool,
    rules: _IngestRules,
    item_tex: str = "",
    saw_figure: bool = False,
) -> ExamQuestion:
    methods = [
        ExamMethod(
            id=method.id,
            label=method.label,
            steps=method.steps,
            steps_symbolic=_symbolic_steps(method.steps),
        )
        for method in acc.methods
    ]
    milestones: list[ExamMilestone] = []
    for role, steps in acc.milestones.items():
        latex = " ; ".join(steps) if steps else acc.milestone_titles.get(role, "")
        milestones.append(
            ExamMilestone(
                role=role,
                title=acc.milestone_titles.get(role, ""),
                latex=latex,
                symbolic=_milestone_symbolic(role, latex, steps),
                steps=steps,
                steps_symbolic=_milestone_steps_symbolic(role, steps),
            )
        )

    graph_points = extract_marked_graph_points(item_tex)
    if rules.rich_section_ingest:
        _merge_marked_milestones(
            milestones,
            acc,
            concept_steps=extract_marked_concepts(item_tex),
            value_table_steps=extract_marked_value_table(item_tex),
        )
    is_graph_figure = bool(rules.graph_kind and saw_figure)
    # Cartesian tikz (e.g. Verifikasi dengan Grafik) is not a number-line figure.
    has_cartesian_tikz = item_has_tikzpicture(item_tex) and not is_graph_figure
    number_line = None
    if is_graph_figure:
        # Gambar Grafik soals: endpoints via graph_points, not HP→number_line.
        pass
    elif has_cartesian_tikz:
        # Sketch present; figure credit without inventing D_f→number_line geometry.
        pass
    elif rules.number_line and expects_figure and final_text:
        number_line = number_line_from_symbolic(
            latex_to_symbolic_payload(final_text)
        )
        if number_line is None:
            number_line = number_line_from_symbolic(final_text)
    elif rules.domain_number_line and final_text:
        claim = domain_claim_from_final(final_text)
        if claim:
            number_line = number_line_from_symbolic(latex_to_symbolic_payload(claim))
            if number_line is None:
                number_line = number_line_from_symbolic(claim)
            if number_line is not None:
                expects_figure = True

    if final_text:
        milestones.append(
            ExamMilestone(
                role="hp",
                latex=final_text,
                symbolic=_final_symbolic(final_text),
            )
        )

    parts: list[ExamPart] = []
    order = 1
    if acc.shared or methods:
        parts.append(ExamPart(kind="algebra", order=order))
        order += 1
    for role in rules.milestone_roles:
        if role in acc.milestones:
            parts.append(ExamPart(kind=role, order=order))
            order += 1
    if expects_figure:
        parts.append(ExamPart(kind="figure", order=order))
        order += 1
    if final_text:
        parts.append(ExamPart(kind="hp", order=order))

    return ExamQuestion(
        number=number,
        part_label=part_label,
        stem=stem,
        stem_symbolic=latex_to_symbolic_payload(stem),
        steps=acc.shared,
        steps_symbolic=_symbolic_steps(acc.shared),
        methods=methods,
        milestones=milestones,
        final=final_text,
        final_symbolic=_final_symbolic(final_text) if final_text else None,
        expects_figure=expects_figure,
        number_line=number_line,
        graph_points=graph_points,
        parts=parts,
    )


def _question_final(item_tex: str, answer: str, rules: _IngestRules) -> str:
    marked = extract_marked_finals(item_tex)
    if marked:
        return join_finals(marked)
    return (rules.extract_final(answer) or "").strip()


def _build_questions(tex: str, pack: TopicPack) -> list[ExamQuestion]:
    """Symbolic payloads are normalized with ``pack``'s capabilities (opt-in ones too)."""
    rules = _rules_for(pack)
    questions: list[ExamQuestion] = []
    with using_pack(pack):
        for index, item in enumerate(split_enumerate_items(prepare_kunci_tex(tex)), start=1):
            questions.extend(_build_item_questions(index, item, rules))
    return questions


def build_exam_schema(
    tex: str,
    *,
    source: str = "",
    topic_id: str = DEFAULT_TOPIC_ID,
    topic_pack: TopicPack | None = None,
) -> ExamSchema:
    """Parse kunci TeX into a full ``ExamSchema`` (stems, steps, HP, figure flags).

    Ingest vocabulary comes from ``topic_pack`` or, when omitted, ``topic_id``'s pack.
    """
    pack = _resolve_pack(topic_pack, topic_id)
    return ExamSchema(
        source=source,
        topic_id=topic_id,
        questions=_build_questions(tex, pack),
    )


def format_recognition_stems_block(
    stems: list[tuple[int, str]] | None,
) -> str:
    """Render ``(number, stem)`` list for crop_math (stems only, no solutions)."""
    if not stems:
        return _NO_EXAM_KEY
    lines = [f"{number}. {stem}" for number, stem in stems if stem.strip()]
    return "\n".join(lines) if lines else _NO_EXAM_KEY


def format_recognition_question_block(schema: ExamSchema | None) -> str:
    """Render stem list for crop_math; include ``[expects_figure]`` flags only.

    Never includes steps or HP.
    """
    if schema is None or not schema.questions:
        return _NO_EXAM_KEY
    lines: list[str] = []
    for question in schema.questions:
        if not question.stem.strip():
            continue
        suffix = " [expects_figure]" if question.expects_figure else ""
        lines.append(f"{question.ref}. {question.stem}{suffix}")
    return "\n".join(lines) if lines else _NO_EXAM_KEY


def load_exam_schema(standard_dir: Path | str) -> ExamSchema | None:
    """Load ``exam_schema.json`` from a standards dir; ``None`` if missing/invalid."""
    path = exam_schema_path(Path(standard_dir))
    if not path.is_file():
        return None
    try:
        return ExamSchema.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ingest_kunci_tex(
    tex: str,
    *,
    source_note: str = "",
    topic_pack: TopicPack | None = None,
) -> list[tuple[int, str]]:
    """Parse kunci TeX into ``(question_number, solution_tex)`` pairs (1-based).

    Honors ``% soal ke N`` for question numbers when present. Sub-soal share
    their parent number; use ``render_question_solutions`` for file naming.
    """
    questions = _build_questions(tex, _resolve_pack(topic_pack, None))
    return [
        (question.number, rendered)
        for question, rendered in render_question_solutions(
            questions, source_note=source_note
        )
    ]


def render_question_solutions(
    questions: list[ExamQuestion],
    *,
    source_note: str = "",
) -> list[tuple[ExamQuestion, str]]:
    """Standard-solution TeX per (sub-)soal that has a final answer or working.

    A soal without a final answer is still written when it has steps or
    methods (proof / prose answers grade on the working).
    """
    results: list[tuple[ExamQuestion, str]] = []
    for question in questions:
        has_work = bool(question.steps or question.methods)
        if not ((question.final or "").strip() or has_work):
            continue
        rendered = render_standard_solution_tex(
            question=question,
            final=question.final,
            source_note=source_note or f"question {question.ref}",
        )
        results.append((question, rendered))
    return results
