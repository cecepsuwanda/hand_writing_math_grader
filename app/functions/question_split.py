"""Split over-merged Questions using exam_schema stems/finals (FP)."""

from __future__ import annotations

import re
from collections import defaultdict

from app.functions.latex_transforms import format_aligned_line, normalize_step_latex
from app.functions.question_names import question_dir_name
from app.models.exam_schema import ExamQuestion, ExamSchema
from app.models.question import Question, SegmentationStatus, StudentStep
from app.models.recognition import SymbolicPayload

_DOLLAR_RE = re.compile(r"\$+")
_HP_PREFIX_RE = re.compile(
    r"^(?:H\.?P\.?|hp)\s*=\s*",
    re.IGNORECASE,
)
_NUMBERED_LINE_RE = re.compile(
    r"(?m)^(?P<label>\d+)\s*\)\s*",
)
# Characters that extend an expression in ``normalize_for_match`` output.
_EXPR_CONTINUATION = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.+-/^<>=(!|")


def normalize_for_match(text: str) -> str:
    """Collapse LaTeX/math text for stem/final comparison."""
    cleaned = (text or "").strip()
    cleaned = _DOLLAR_RE.sub("", cleaned)
    cleaned = cleaned.replace(r"\left", "").replace(r"\right", "")
    cleaned = cleaned.replace(r"\leq", "<=").replace(r"\le", "<=")
    cleaned = cleaned.replace(r"\geq", ">=").replace(r"\ge", ">=")
    cleaned = cleaned.replace(r"\neq", "!=").replace(r"\ne", "!=")
    cleaned = cleaned.replace(r"\infty", "oo").replace(r"\cdot", "*")
    cleaned = cleaned.replace(r"\times", "*")
    cleaned = cleaned.replace(r"\frac", "")
    cleaned = cleaned.replace("{", "").replace("}", "")
    cleaned = cleaned.replace("\\", "")
    cleaned = cleaned.replace("*", "")
    cleaned = cleaned.replace(" ", "").replace("&", "")
    cleaned = cleaned.lower()
    return cleaned


def step_text(step: StudentStep) -> str:
    """Prefer symbolic.repr, then raw_text, then latex."""
    if step.symbolic is not None and (step.symbolic.repr or "").strip():
        return step.symbolic.repr.strip()
    raw = (step.raw_text or "").strip()
    if raw:
        return raw
    return (step.latex or "").strip()


def _strip_hp_prefix(text: str) -> str:
    return _HP_PREFIX_RE.sub("", text.strip()).strip()


def schema_stem_text(exam_question: ExamQuestion) -> str:
    """Prefer ``stem_symbolic.repr``; fall back to LaTeX stem."""
    if (
        exam_question.stem_symbolic is not None
        and (exam_question.stem_symbolic.repr or "").strip()
    ):
        return exam_question.stem_symbolic.repr.strip()
    return (exam_question.stem or "").strip()


def schema_final_text(exam_question: ExamQuestion) -> str:
    """Prefer ``final_symbolic.repr``; fall back to LaTeX final."""
    if (
        exam_question.final_symbolic is not None
        and (exam_question.final_symbolic.repr or "").strip()
    ):
        return exam_question.final_symbolic.repr.strip()
    return (exam_question.final or "").strip()


def _is_bounded_at(haystack: str, start: int, end: int) -> bool:
    """Embedded match must not continue an expression (``2x-1<5`` inside ``2x-1<5x+2``)."""
    before = haystack[start - 1] if start > 0 else ""
    after = haystack[end] if end < len(haystack) else ""
    return (not before or before not in _EXPR_CONTINUATION) and (
        not after or after not in _EXPR_CONTINUATION
    )


def match_schema_stem(text: str, exam_question: ExamQuestion) -> bool:
    """True if ``text`` looks like the problem stem (not an intermediate step)."""
    a = normalize_for_match(text)
    b = normalize_for_match(schema_stem_text(exam_question))
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow stem embedded in longer LLM raw (e.g. "1) 2-3x<=12")
    if len(b) < 5:
        return False
    start = a.find(b)
    while start >= 0:
        if _is_bounded_at(a, start, start + len(b)):
            return True
        start = a.find(b, start + 1)
    return False


def match_schema_final(text: str, exam_question: ExamQuestion) -> bool:
    """True if ``text`` matches schema final / HP.

    Uses equality after normalize only — substring matching wrongly equates
    ``x>1`` with ``x>10``.
    """
    final = schema_final_text(exam_question)
    if not final:
        return False
    a = normalize_for_match(_strip_hp_prefix(text))
    b = normalize_for_match(_strip_hp_prefix(final))
    if not a or not b:
        return False
    return a == b


def _is_figure_step(step: StudentStep) -> bool:
    return step.symbolic is not None and step.symbolic.kind == "figure"


def _find_stem_number(text: str, schema_questions: list[ExamQuestion]) -> int | None:
    """Return schema question number whose stem matches ``text``, or None."""
    # Prefer longer stems to avoid ambiguous short matches.
    ranked = sorted(
        schema_questions,
        key=lambda q: len(normalize_for_match(schema_stem_text(q))),
        reverse=True,
    )
    for exam_q in ranked:
        if match_schema_stem(text, exam_q):
            return exam_q.number
    return None


def _rebuild_latex_from_steps(steps: list[StudentStep]) -> str:
    lines: list[str] = []
    for step in steps:
        if _is_figure_step(step):
            continue
        expr = normalize_step_latex(step)
        if not expr:
            continue
        lines.append(format_aligned_line(expr) + r" \\")
    if not lines:
        return ""
    if lines[-1].endswith(r" \\"):
        lines[-1] = lines[-1][: -len(r" \\")]
    body = "\n".join(lines)
    return f"\\begin{{aligned}}\n{body}\n\\end{{aligned}}"


def split_latex_by_schema(
    latex: str,
    schema: ExamSchema,
    numbers: list[int],
) -> dict[int, str]:
    """Split a multi-question latex blob by numbered ``N)`` markers or stems."""
    latex = (latex or "").strip()
    if not latex or len(numbers) <= 1:
        return {numbers[0]: latex} if numbers else {}

    by_number = {q.number: q for q in schema.questions}
    # Prefer explicit "N)" markers from recognition latex.
    matches = list(_NUMBERED_LINE_RE.finditer(latex))
    if len(matches) >= 2:
        result: dict[int, str] = {}
        for index, match in enumerate(matches):
            label = int(match.group("label"))
            if label not in numbers:
                continue
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(latex)
            chunk = latex[start:end].strip()
            if chunk:
                result[label] = chunk
        if len(result) >= 2:
            return result

    # Stem-based cut: find first occurrence of next stem in latex text.
    result = {}
    remaining = latex
    ordered = [n for n in numbers if n in by_number]
    for index, num in enumerate(ordered):
        exam_q = by_number[num]
        stem_norm = normalize_for_match(schema_stem_text(exam_q))
        if index + 1 < len(ordered):
            next_q = by_number[ordered[index + 1]]
            next_stem = normalize_for_match(schema_stem_text(next_q))
            # Scan original remaining for a line that normalizes to contain next stem
            cut = None
            for line_match in re.finditer(r"(?m)^.*$", remaining):
                line = line_match.group(0)
                if next_stem and next_stem in normalize_for_match(line):
                    cut = line_match.start()
                    break
            if cut is not None and cut > 0:
                result[num] = remaining[:cut].strip()
                remaining = remaining[cut:].strip()
                continue
        result[num] = remaining.strip()
        remaining = ""
        if stem_norm:
            pass
    return {k: v for k, v in result.items() if v}


def _build_split_question(
    *,
    number: int,
    steps: list[StudentStep],
    source: Question,
    exam_question: ExamQuestion | None,
    owns_source_final: bool,
    owns_figures: bool,
) -> Question:
    renumbered: list[StudentStep] = []
    for index, step in enumerate(steps, start=1):
        renumbered.append(step.model_copy(update={"step_number": index}))

    final_answer = ""
    final_symbolic: SymbolicPayload | None = None
    if owns_source_final:
        final_answer = source.student_final_answer
        final_symbolic = source.student_final_symbolic
    elif exam_question is not None:
        for step in reversed(renumbered):
            if _is_figure_step(step):
                continue
            text = step_text(step)
            if match_schema_final(text, exam_question) or _HP_PREFIX_RE.match(text):
                final_answer = text
                final_symbolic = step.symbolic
                break
    if not final_answer and renumbered:
        last = renumbered[-1]
        if not _is_figure_step(last):
            final_answer = step_text(last)
            final_symbolic = last.symbolic

    return Question(
        question_id=question_dir_name(number),
        question_number=number,
        page_references=list(source.page_references),
        image_regions=list(source.image_regions),
        student_steps=renumbered,
        student_final_answer=final_answer,
        student_final_symbolic=final_symbolic,
        figure_refs=list(source.figure_refs) if owns_figures else [],
        confidence=source.confidence,
        segmentation_status=SegmentationStatus.MERGED,
    )


def _source_final_owner(source: Question, buckets: dict[int, list[StudentStep]]) -> int | None:
    """Bucket whose steps contain the recognized final answer (None if not found)."""
    final = (source.student_final_answer or "").strip()
    symbolic = source.student_final_symbolic
    targets = {
        normalize_for_match(_strip_hp_prefix(text))
        for text in (final, symbolic.repr if symbolic is not None else "")
        if (text or "").strip()
    }
    targets.discard("")
    if not targets:
        return None
    owners = [
        number
        for number, steps in buckets.items()
        if any(
            normalize_for_match(_strip_hp_prefix(text)) in targets
            for step in steps
            for text in (step_text(step), step.raw_text or "")
            if text
        )
    ]
    return owners[-1] if owners else None


def _figure_owner(
    buckets: dict[int, list[StudentStep]],
    by_schema: dict[int, ExamQuestion],
    default_number: int,
) -> int:
    """The only part expecting a figure; otherwise the source's own number (or the first part)."""
    expecting = [
        number
        for number in buckets
        if (exam := by_schema.get(number)) is not None and exam.expects_figure
    ]
    if len(expecting) == 1:
        return expecting[0]
    if default_number in buckets:
        return default_number
    return min(buckets)


def _split_one_question(
    question: Question,
    schema: ExamSchema,
) -> list[Question]:
    schema_questions = sorted(schema.questions, key=lambda q: q.number)
    if len(schema_questions) < 2 or not question.student_steps:
        return [question]

    buckets: dict[int, list[StudentStep]] = defaultdict(list)
    current: int | None = None
    default_number = question.question_number
    if default_number < 1:
        default_number = schema_questions[0].number

    for step in question.student_steps:
        text = step_text(step)
        stem_num = None if _is_figure_step(step) else _find_stem_number(text, schema_questions)
        if stem_num is not None:
            current = stem_num
        if current is None:
            current = default_number
        buckets[current].append(step)

    if len(buckets) <= 1:
        return [question]

    by_schema = {q.number: q for q in schema_questions}
    final_owner = _source_final_owner(question, buckets)
    figure_owner = _figure_owner(buckets, by_schema, default_number)
    result: list[Question] = []
    for number in sorted(buckets):
        result.append(
            _build_split_question(
                number=number,
                steps=buckets[number],
                source=question,
                exam_question=by_schema.get(number),
                owns_source_final=number == final_owner,
                owns_figures=number == figure_owner,
            )
        )
    return result


def _store_latex(store: dict[int, str], question_number: int, chunk: str) -> None:
    """Keep every fragment's LaTeX when two splits share a question number."""
    body = chunk.strip()
    if not body:
        return
    previous = store.get(question_number, "").strip()
    if not previous:
        store[question_number] = body
        return
    if body in previous:
        return
    store[question_number] = f"{previous}\n\n{body}"


def assign_provisional_by_stem(
    questions: list[Question],
    schema: ExamSchema | None,
    latex_by_number: dict[int, str] | None = None,
) -> tuple[list[Question], dict[int, str]]:
    """Give an unnumbered crop the key number whose stem its first step copies.

    Only a provisional question outside the key is renumbered, and only to a
    number no numbered crop was read as and no earlier provisional crop took;
    otherwise it keeps its provisional number. The status stays ``PROVISIONAL``
    so the assignment can still be checked.
    """
    latex = dict(latex_by_number or {})
    if schema is None or not schema.questions:
        return list(questions), latex

    key_numbers = {q.number for q in schema.questions}
    taken = {
        q.question_number
        for q in questions
        if q.segmentation_status != SegmentationStatus.PROVISIONAL
    }
    result: list[Question] = []
    for question in questions:
        number = question.question_number
        if (
            question.segmentation_status != SegmentationStatus.PROVISIONAL
            or number in key_numbers
        ):
            result.append(question)
            continue
        first = next((s for s in question.student_steps if not _is_figure_step(s)), None)
        stem_number = (
            _find_stem_number(step_text(first), schema.questions)
            if first is not None
            else None
        )
        if stem_number is None or stem_number in taken:
            result.append(question)
            continue
        taken.add(stem_number)
        if number in latex:
            latex[stem_number] = latex.pop(number)
        result.append(
            question.model_copy(
                update={
                    "question_number": stem_number,
                    "question_id": question_dir_name(stem_number),
                }
            )
        )
    result.sort(key=lambda q: q.question_number)
    return result, latex


def split_questions_by_exam_schema(
    questions: list[Question],
    schema: ExamSchema | None,
    latex_by_number: dict[int, str] | None = None,
) -> tuple[list[Question], dict[int, str]]:
    """Split over-merged questions using schema stems; also remap latex blobs.

    Returns ``(questions, latex_by_number)``. No-op when schema is missing/short.
    """
    latex_by_number = dict(latex_by_number or {})
    if schema is None or len(schema.questions) < 2:
        return questions, latex_by_number

    split_out: list[Question] = []
    new_latex: dict[int, str] = {}
    claimed_numbers: set[int] = set()

    for question in questions:
        parts = _split_one_question(question, schema)
        if len(parts) == 1:
            split_out.append(parts[0])
            qnum = parts[0].question_number
            if qnum in latex_by_number:
                _store_latex(new_latex, qnum, latex_by_number[qnum])
            claimed_numbers.add(qnum)
            continue

        source_latex = latex_by_number.get(question.question_number, "")
        # Do not steal latex keyed under other question numbers.

        numbers = [p.question_number for p in parts]
        latex_parts = split_latex_by_schema(source_latex, schema, numbers)
        for part in parts:
            split_out.append(part)
            claimed_numbers.add(part.question_number)
            chunk = latex_parts.get(part.question_number, "").strip()
            if not chunk:
                chunk = _rebuild_latex_from_steps(part.student_steps)
            _store_latex(new_latex, part.question_number, chunk)

    # Preserve latex for numbers never touched
    kept_numbers = {q.question_number for q in split_out}
    for qnum, body in latex_by_number.items():
        if qnum not in new_latex and qnum in kept_numbers:
            _store_latex(new_latex, qnum, body)

    split_out.sort(key=lambda q: q.question_number)
    # Coalesce duplicate numbers (e.g. split created Q2 while another fragment was already Q2).
    coalesced: dict[int, Question] = {}
    for question in split_out:
        existing = coalesced.get(question.question_number)
        if existing is None:
            coalesced[question.question_number] = question
            continue
        combined_steps = list(existing.student_steps) + list(question.student_steps)
        renumbered = [
            step.model_copy(update={"step_number": index})
            for index, step in enumerate(combined_steps, start=1)
        ]
        pages = sorted(set(existing.page_references) | set(question.page_references))
        coalesced[question.question_number] = existing.model_copy(
            update={
                "student_steps": renumbered,
                "page_references": pages,
                "image_regions": list(existing.image_regions) + list(question.image_regions),
                "figure_refs": list(existing.figure_refs) + list(question.figure_refs),
                "student_final_answer": question.student_final_answer
                or existing.student_final_answer,
                "student_final_symbolic": question.student_final_symbolic
                or existing.student_final_symbolic,
            }
        )
    result_questions = [coalesced[n] for n in sorted(coalesced)]
    return result_questions, new_latex
