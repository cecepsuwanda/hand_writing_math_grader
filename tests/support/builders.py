"""Model builders: small factories for domain objects and on-disk fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf
from PIL import Image

from app.functions.question_crops import write_question_crops
from app.functions.question_names import (
    latex_source_filename,
    question_artifact_filename,
    question_dir_name,
)
from app.functions.run_layout import RunLayout
from app.models.grading import (
    ErrorType,
    QuestionGrade,
    ReviewStatus,
    Rubric,
    RubricCriterion,
    StepGrade,
    StepGradeStatus,
)
from app.models.page import Page
from app.models.process import ProcessResult
from app.models.question import FigureRef, Question, StudentStep
from app.models.recognition import PageRecognition, SymbolicPayload
from app.models.report import (
    ExamReport,
    PromptVersions,
    QuestionReportRow,
    ReportMetadata,
    ReportResult,
)
from app.models.validation import (
    QuestionValidation,
    StepValidation,
    ValidationMethod,
    ValidationStatus,
)

StatusSpec = ValidationStatus | tuple[ValidationStatus, str]
SymbolicSpec = str | SymbolicPayload | None

MINI_KUNCI = r"""
\begin{document}
\begin{enumerate}
    \item $2-3x \le 12$
    \begin{itemize}
    \item Langkah-langkah
    \begin{align}
    2 - 3x &\leq 12 \quad \text{(awal)} \\
    x &\geq -\frac{10}{3}
    \end{align}
    \item HP: $\left[-\frac{10}{3}, \infty\right)$
    \end{itemize}

    \item $3x-5 < 4x-6$
    \begin{itemize}
    \item Langkah-langkah
    \begin{align}
    3x - 5 &< 4x - 6 \\
    x &> 1
    \end{align}
    \item HP: $(1, \infty)$
    \end{itemize}
\end{enumerate}
\end{document}
"""

Q1_KUNCI = r'''
\begin{enumerate}
\item $2-3x \le 12$
\begin{itemize}
\item Langkah-langkah Penyelesaian
\begin{align}
2 - 3x &\leq 12 \quad \text{(Pertidaksamaan awal)} \\
2 - 3x - 2 &\leq 12 - 2 \quad \text{(Kurangi 2 pada kedua ruas)} \\
-3x &\leq 10 \quad \text{(Sederhanakan)} \\
-3x \cdot \left(-\frac{1}{3}\right) &\geq 10 \cdot \left(-\frac{1}{3}\right) \quad \text{(Kali kedua ruas dengan $-\frac{1}{3}$)} \\
x &\geq -\frac{10}{3} \quad \text{(Sederhanakan, tanda berubah)}
\end{align}
\item HP: $\left[-\frac{10}{3}, \infty\right)$
\end{itemize}
\end{enumerate}
'''

# PyMuPDF refuses to save a document with zero pages, so keep a minimal PDF.
_EMPTY_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)


# --- files ---------------------------------------------------------------


def write_pdf(path: Path, page_count: int) -> Path:
    if page_count < 0:
        raise ValueError("page_count must be >= 0")
    if page_count == 0:
        path.write_bytes(_EMPTY_PDF)
        return path

    document = pymupdf.open()
    for _ in range(page_count):
        document.new_page()
    document.save(path)
    document.close()
    return path


def write_png(
    path: Path,
    size: tuple[int, int] = (200, 200),
    color: tuple[int, int, int] = (240, 240, 240),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path)
    return path


def write_fake_png_bytes(tmp_path: Path, name: str = "page.png") -> Path:
    """PNG magic + junk: enough for code that only base64-encodes the file."""
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return path


def write_recognition(path: Path, page: PageRecognition) -> Path:
    path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_crop_workspace(pages_dir: Path, crops_dir: Path) -> Path:
    """One-page ``pages.json`` + empty ink regions: input for ``process_from_crops``."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "pages.json").write_text(
        '[{"page_number":1,"image":"page_001.png","width":10,"height":10}]',
        encoding="utf-8",
    )
    regions = crops_dir / "page_001" / "page_001_regions.json"
    regions.parent.mkdir(parents=True, exist_ok=True)
    regions.write_text('{"page_number":1,"source":"ink","regions":[]}', encoding="utf-8")
    return regions


def write_question_dir(
    questions_dir: Path, question: Question, *, latex_source: str = ""
) -> Path:
    """``questions/<question_id>/question.json`` (+ optional ``latex_source.tex``)."""
    folder = questions_dir / question.question_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / question_artifact_filename()
    path.write_text(question.model_dump_json(indent=2), encoding="utf-8")
    if latex_source:
        (folder / latex_source_filename()).write_text(latex_source, encoding="utf-8")
    return path


def write_config(
    tmp_path: Path,
    *,
    vision_model: str | None = "vision-test",
    reasoning_model: str | None = None,
    jawaban_dir: Path | None = None,
    output_root: Path | None = None,
    standards_root: Path | None = None,
    topic_id: str | None = None,
) -> Path:
    """Write ``config.yaml``; ``None`` omits a key (``vision_model=''`` keeps it empty)."""
    lines: list[str] = []
    if vision_model is not None or reasoning_model is not None:
        lines.append("ollama:")
        if vision_model is not None:
            lines.append(f'  vision_model: "{vision_model}"')
        if reasoning_model is not None:
            lines.append(f'  reasoning_model: "{reasoning_model}"')
    if jawaban_dir is not None:
        lines += ["input:", f"  jawaban_dir: {jawaban_dir.as_posix()}"]
    if output_root is not None:
        lines += ["output:", f"  root_dir: {output_root.as_posix()}"]
    if standards_root is not None or topic_id is not None:
        lines.append("grading:")
        if standards_root is not None:
            lines.append(f"  standards_root: {standards_root.as_posix()}")
        if topic_id is not None:
            lines.append(f'  topic_id: "{topic_id}"')
    path = tmp_path / "config.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def single_question_json(question_number: int, relation: str) -> str:
    """Crop-math response with one relation step (vision recognizer payload)."""
    return json.dumps(
        {
            "question_number": question_number,
            "steps": [
                {
                    "step_number": 1,
                    "raw_text": relation,
                    "symbolic": {"kind": "relation", "repr": relation},
                    "confidence": 0.9,
                }
            ],
            "final_answer": relation,
            "final_answer_symbolic": None,
            "latex_document": relation,
            "confidence": 0.9,
        }
    )


# --- questions -------------------------------------------------------------


def symbolic(value: SymbolicSpec, kind: str = "relation") -> SymbolicPayload | None:
    if value is None or isinstance(value, SymbolicPayload):
        return value
    return SymbolicPayload(kind=kind, repr=value)


def make_step(
    number: int,
    latex: str = "",
    *,
    raw_text: str = "",
    symbolic_repr: SymbolicSpec = None,
    role: str | None = None,
    confidence: float | None = None,
) -> StudentStep:
    return StudentStep(
        step_number=number,
        raw_text=raw_text,
        latex=latex,
        symbolic=symbolic(symbolic_repr),
        role=role,
        confidence=confidence,
    )


def make_figure(
    repr_: str | None = None,
    *,
    caption: str = "",
    path: str = "fig.png",
    kind: str = "figure",
) -> FigureRef:
    return FigureRef(path=path, caption=caption, symbolic=symbolic(repr_, kind))


def make_question(
    *latex: str,
    number: int = 1,
    final: str = "",
    final_symbolic: SymbolicSpec = None,
    steps: list[StudentStep] | None = None,
    figures: list[FigureRef] | None = None,
    raw_text: str = "",
) -> Question:
    """Question from LaTeX step strings (or explicit ``steps``); id follows ``number``."""
    student_steps = (
        steps
        if steps is not None
        else [make_step(i, text, raw_text=raw_text) for i, text in enumerate(latex, start=1)]
    )
    return Question(
        question_id=f"question_{number:03d}",
        question_number=number,
        student_steps=student_steps,
        student_final_answer=final,
        student_final_symbolic=symbolic(final_symbolic),
        figure_refs=figures or [],
    )


RATIONAL_INEQUALITY_STEPS: tuple[tuple[str, str], ...] = (
    ("(x+2)/(x+4) < (x-1)/(x-2)", "algebra"),
    ("(x+2)/(x+4) - (x-1)/(x-2) < 0", "algebra"),
    ("((x+2)*(x-2) - (x-1)*(x+4))/((x+4)*(x-2)) < 0", "algebra"),
    ("((x**2-4) - (x**2+3*x-4))/((x+4)*(x-2)) < 0", "algebra"),
    ("(x**2-4-x**2-3*x+4)/((x+4)*(x-2)) < 0", "algebra"),
    ("-3*x/((x+4)*(x-2)) < 0", "algebra"),
    ("-3x=0 and x=0", "critical_points"),
    ("x+4=0 and x=-4", "critical_points"),
    ("x-2=0 and x=2", "critical_points"),
    ("(-4, 0) U (2, oo)", "hp"),
    ("(-3*(-5))/((-5+4)*(-5-2)) = 15/7", "sign_chart"),
    ("(-3*(-2))/((-2+4)*(-2-2)) = -3/4", "sign_chart"),
    ("(-3*1)/((1+4)*(1-2)) = 3/5", "sign_chart"),
    ("(-3*3)/((3+4)*(3-2)) = -9/7", "sign_chart"),
)


def make_rational_inequality_question(
    *,
    replace: dict[int, str] | None = None,
    final_symbolic: str = "(-4, 0) U (2, oo)",
) -> Question:
    """Role-tagged (x+2)/(x+4) < (x-1)/(x-2) solution; ``replace`` swaps reprs by step number."""
    overrides = replace or {}
    steps = [
        make_step(number, symbolic_repr=overrides.get(number, repr_), role=role)
        for number, (repr_, role) in enumerate(RATIONAL_INEQUALITY_STEPS, start=1)
    ]
    return make_question(steps=steps, number=7, final_symbolic=final_symbolic)


# --- validation / grading ------------------------------------------------------


def make_step_validation(
    number: int, status: ValidationStatus, reason: str = ""
) -> StepValidation:
    return StepValidation(
        step_number=number,
        status=status,
        method=ValidationMethod.SYMPY,
        reason=reason or status.value,
    )


def _step_validation(number: int, spec: StatusSpec) -> StepValidation:
    if isinstance(spec, tuple):
        return make_step_validation(number, *spec)
    return make_step_validation(number, spec)


def make_validation(
    *statuses: StatusSpec,
    final: StatusSpec | None = ValidationStatus.VALID,
    number: int = 1,
) -> QuestionValidation:
    """Steps numbered from 1; each spec is a status or ``(status, reason)``."""
    return QuestionValidation(
        question_number=number,
        question_id=f"question_{number:03d}",
        steps=[_step_validation(i, spec) for i, spec in enumerate(statuses, start=1)],
        final_answer_status=None if final is None else _step_validation(0, final),
    )


def sample_rubric() -> Rubric:
    return Rubric(
        question=1,
        maximum_score=10,
        criteria=[
            RubricCriterion(id="setup", points=2),
            RubricCriterion(id="transformation", points=4),
            RubricCriterion(id="calculation", points=2),
            RubricCriterion(id="final_answer", points=2),
        ],
    )


def make_step_grade(
    number: int,
    score: float,
    max_score: float,
    *,
    status: StepGradeStatus = StepGradeStatus.CORRECT,
    validation: ValidationStatus = ValidationStatus.VALID,
    part_id: str | None = None,
) -> StepGrade:
    return StepGrade(
        step_number=number,
        score=score,
        max_score=max_score,
        status=status,
        error_type=ErrorType.NONE,
        feedback="",
        validation_status=validation,
        part_id=part_id,
    )


def make_report_question_grade(
    number: int,
    score: float,
    maximum: float,
    *,
    review: ReviewStatus = ReviewStatus.AUTO_ACCEPT,
    steps: int = 2,
) -> QuestionGrade:
    per = maximum / max(steps, 1)
    return QuestionGrade(
        question_id=f"question_{number:03d}",
        question_number=number,
        score=score,
        maximum_score=maximum,
        steps=[
            make_step_grade(i + 1, per if i < steps - 1 else score - per * (steps - 1), per)
            for i in range(steps)
        ],
        review_status=review,
    )


def make_process_question_grade() -> QuestionGrade:
    return QuestionGrade(
        question_id="question_001",
        question_number=1,
        score=8.0,
        maximum_score=10.0,
        review_status=ReviewStatus.AUTO_ACCEPT,
    )


# --- pipeline / report -----------------------------------------------------------


def make_page(number: int = 1) -> Page:
    return Page(page_number=number, image=f"page_{number:03d}.png", width=100, height=100)


def make_report_metadata(tmp_path: Path) -> ReportMetadata:
    return ReportMetadata(
        generated_at="2026-01-01T00:00:00+00:00",
        standard_dir=tmp_path / "standards" / "topik_1",
        questions_dir=tmp_path / "questions",
        student_id="student_001",
        vision_model="vision-test",
        reasoning_model="reason-test",
        prompt_versions=PromptVersions(
            recognition="recognition-v1", validation="validation-v1", grading="grading-v1"
        ),
    )


def make_report_result(tmp_path: Path) -> ReportResult:
    out = tmp_path / "output"
    meta = ReportMetadata(
        generated_at="2026-01-01T00:00:00+00:00",
        standard_dir=tmp_path / "standards",
        questions_dir=tmp_path / "questions",
        student_id="student_001",
        prompt_versions=PromptVersions(),
    )
    exam = ExamReport(
        metadata=meta,
        questions=[
            QuestionReportRow(
                question_id="question_001",
                question_number=1,
                score=8.0,
                maximum_score=10.0,
                review_status=ReviewStatus.AUTO_ACCEPT,
                step_count=2,
            )
        ],
        total_score=8.0,
        maximum_total=10.0,
        overall_status=ReviewStatus.AUTO_ACCEPT,
    )
    return ReportResult(
        exam_report=exam,
        output_dir=out,
        report_json_path=out / "report.json",
        summary_csv_path=out / "summary.csv",
        report_html_path=out / "report.html",
    )


def write_report_workspace(
    root: Path,
    question: Question,
    grade: QuestionGrade | None = None,
    *,
    crops: list[str] | None = None,
    mapped_crops: list[str] | None = None,
    stem: str = "",
) -> RunLayout:
    """Run folder with ``question.json`` (+ ``grading.json``) and crop PNGs.

    ``crops`` are written as PNGs under ``crops/page_NNN/``; ``mapped_crops``
    (may name missing files) goes to ``crops/question_crops/`` when given.
    """
    layout = RunLayout(root=root)
    qdir = layout.questions_dir / question_dir_name(question.question_number)
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / "question.json").write_text(question.model_dump_json(indent=2), encoding="utf-8")
    if grade is not None:
        (qdir / "grading.json").write_text(grade.model_dump_json(indent=2), encoding="utf-8")
    for name in crops or []:
        write_png(layout.crops_dir / name.split("_region_", 1)[0] / name, size=(40, 20))
    if mapped_crops is not None:
        write_question_crops(
            layout.crops_dir,
            {question.question_number: list(mapped_crops)},
            stems={question.question_number: stem},
        )
    return layout


def make_process_result(root: Path, **overrides) -> ProcessResult:
    """Empty ``ProcessResult`` under ``root``; override any field by keyword."""
    fields = {
        "student_id": "student_001",
        "output_dir": root / "output",
        "questions_dir": root / "questions",
        "pages_dir": root / "pages",
        "recognition_dir": root / "recognition",
    }
    fields.update(overrides)
    return ProcessResult(**fields)
