"""Model builders: small factories for domain objects and on-disk fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

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

# tugas_topik_1.tex style: \textbf{Jawab:}, \textbf{Langkah N: ...}, methods
# nested under the critical-points step, $\text{HP} = ...$.
TOPIK1_KUNCI = r'''
\begin{enumerate}
%===========================================================
\item $2x^2 - 5x - 3 < 0$

\textbf{Jawab:}

\begin{itemize}
\item \textbf{Langkah 1: Ubah ke Bentuk Baku}
\begin{align}
2x^2 - 5x - 3 &< 0 \quad \text{(Pertidaksamaan awal)} \\
\text{Cari akar-akar persamaan } 2x^2 - 5x - 3 &= 0
\end{align}

\item \textbf{Langkah 2: Tentukan Titik Kritis}

\begin{itemize}
\item \textit{Metode 1: Pemfaktoran}
\begin{align}
(2x + 1)(x - 3) &= 0 \quad \text{(Faktorkan)} \\
x &= -\frac{1}{2} \quad \text{atau} \quad x = 3
\end{align}

\item \textit{Metode 2: Rumus ABC}
\begin{align}
x_1,x_2 &= \frac{-b \pm \sqrt{b^2 - 4ac}}{2a} \\
x_1 &= 3
\end{align}
\end{itemize}

\item \textbf{Langkah 3: Analisis Tanda}
\begin{align}
\text{Selang } x < -\frac{1}{2}: \quad &\text{Pilih } x = -1
\end{align}

\item \textbf{Langkah 4: Gambar Garis Bilangan}
\begin{center}
\begin{tikzpicture}
\draw (0,0)--(1,0);
\end{tikzpicture}
\end{center}

\item \textbf{Langkah 5: Tentukan HP}

$\text{HP} = \left(-\frac{1}{2}, 3\right)$
\end{itemize}
\end{enumerate}
'''

# tugas_topik_2.tex style: alternative ``Cara N`` paths, each a full nested
# itemize of Langkah; extra prose after Jawab; HP written as a chain.
TOPIK2_KUNCI = r'''
\begin{enumerate}
\item $|x + 2| < 1$

\textbf{Jawab:}

\begin{itemize}
\item \textbf{Cara 1: Sifat 2, $|x| < a \iff -a < x < a$}

\begin{itemize}
\item \textbf{Langkah 1: Terapkan Sifat 2}
\begin{align}
|x+2| &< 1 \\
-3 &< x < -1 \quad \text{(Solusi)}
\end{align}

\item \textbf{Langkah 2: Tentukan HP}

$\text{HP} = (-3, -1)$
\end{itemize}

\item \textbf{Cara 2: Sifat 1, $|x| = \sqrt{x^2}$}

\begin{itemize}
\item \textbf{Langkah 1: Terapkan Sifat 1}
\begin{align}
(x+2)^2 &< 1 \\
(x + 1)(x + 3) &< 0
\end{align}

\item \textbf{Langkah 2: Tentukan Titik Kritis}
\begin{align}
x + 1 &= 0 \Rightarrow x = -1
\end{align}

\item \textbf{Langkah 3: Gambar Garis Bilangan}
\begin{center}
\begin{tikzpicture}
\draw (0,0)--(1,0);
\end{tikzpicture}
\end{center}

\item \textbf{Langkah 4: Tentukan HP}

$\text{HP} = (-3, -1)$
\end{itemize}
\end{itemize}

%===========================================================
\item $\displaystyle \left|\frac{x-1}{3x+1}\right| \leq \frac{7}{2}$

\textbf{Jawab:}

Syarat penyebut: $3x + 1 \neq 0$, sehingga $x \neq -\frac{1}{3}$.

\begin{itemize}
\item \textbf{Cara 1: Sifat 2, $|x| \leq a \iff -a \leq x \leq a$}

\begin{itemize}
\item \textbf{Langkah 1: Terapkan Sifat 2}
\begin{align}
-\frac{7}{2} &\leq \frac{x-1}{3x+1} \leq \frac{7}{2}
\end{align}

\item \textbf{Langkah 2: Tentukan HP}

$\text{HP} = \left(\left(-\infty, -\frac{1}{3}\right) \cup \left[-\frac{5}{23}, \infty\right)\right) \cap \left(\left(-\infty, -\frac{9}{19}\right] \cup \left(-\frac{1}{3}, \infty\right)\right) = \left(-\infty, -\frac{9}{19}\right] \cup \left[-\frac{5}{23}, \infty\right)$
\end{itemize}
\end{itemize}
\end{enumerate}
'''

# tugas_topik_3.tex style: a soal listing sub-questions (a)/(b) in its statement,
# answered by one shared Jawab; the list belongs to the stem.
TOPIK3_KUNCI = r'''
\begin{enumerate}
\item Diketahui $f(x) = \sqrt{x}$ dan $g(x) = x^2$.
\begin{enumerate}
  \item Periksa apakah $(f \circ g)$ ada?
  \item Jika ada, tentukan $(f \circ g)(x)$.
\end{enumerate}

\textbf{Jawab:}
\begin{itemize}
\item \textbf{Langkah 1: Bagian (a), Periksa Syarat}
\begin{align}
R_g \cap D_f &= [0, \infty) \neq \emptyset
\end{align}
\item \textbf{Langkah 2: Bagian (b), Rumus}
\begin{align}
(f \circ g)(x) &= \sqrt{x^2} = |x|
\end{align}
\end{itemize}
\end{enumerate}
'''

# tugas_topik_4.tex style: soal 1 = nested enumerate whose items each carry a
# Jawab (sub-soal 1a, 1b); soal 2 = one Jawab answering ``\item[(a)]`` /
# ``\item[(b)]`` listed in a tabular under a stem figure.
TOPIK4_KUNCI = r'''
\begin{enumerate}
\item Hitunglah nilai limit fungsi berikut:
\begin{enumerate}
\item $\displaystyle\lim_{x \to -1} (1 - 2x)$

\textbf{Jawab:}
\begin{itemize}
\item \textbf{Langkah 1: Substitusi Langsung}
\begin{align}
\lim_{x \to -1} (1 - 2x) &= 1 - 2(-1) \quad \text{(Substitusi $x = -1$)} \\
&= 1 + 2 = 3
\end{align}
% final: 3
\end{itemize}

\item $\displaystyle\lim_{t \to 3} \frac{t^2 + 4t - 21}{t - 3}$

\textbf{Jawab:}
\begin{itemize}
\item \textbf{Langkah 1: Faktorkan}
\begin{align}
\lim_{t \to 3} \frac{t^2 + 4t - 21}{t - 3} &= \lim_{t \to 3} (t + 7) = 10
\end{align}
% final: 10
\end{itemize}
\end{enumerate}

\item Diberikan grafik fungsi berikut:
\begin{center}
\begin{tikzpicture}
\draw (0,1)--(1,0);
\end{tikzpicture}
\end{center}
Cari limit/nilai fungsi berikut.
\begin{center}
\begin{tabular}{ll}
(a) $\displaystyle\lim_{x \to 1^-} f(x)$ & (b) $f(2)$
\end{tabular}
\end{center}

\textbf{Jawab:}
\begin{itemize}
\item \textbf{Langkah 1: Baca Limit}
\begin{enumerate}
  \item[(a)] Dari kiri $x = 1$:
  \begin{align}
  \lim_{x \to 1^-} f(x) &= \lim_{x \to 1^-} (-x + 1) = 0
  \end{align}
  % final: 0
\end{enumerate}
\item \textbf{Langkah 2: Baca Nilai Fungsi}
\begin{enumerate}
  \item[(b)] Titik penuh di $x = 2$ adalah $(2,2)$, jadi $f(2) = 2$.
  % final: 2
\end{enumerate}
\end{itemize}
\end{enumerate}
'''

KUNCI_DIR = Path(__file__).resolve().parents[2] / "data" / "input" / "kunci_jawaban"


def read_kunci(name: str) -> str:
    """Repo kunci file (``tugas_topik_4.tex``) for chapter acceptance tests."""
    return (KUNCI_DIR / name).read_text(encoding="utf-8")


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


def new_page(
    size: tuple[int, int], paper: tuple[int, int, int] = (255, 255, 255)
) -> Image.Image:
    return Image.new("RGB", size, color=paper)


def draw_writing(
    image: Image.Image,
    box: tuple[int, int, int, int],
    ink: tuple[int, int, int] = (20, 20, 20),
) -> Image.Image:
    """Fill ``box`` (x0, y0, x1, y1) with 3 px strokes every 6 px, like lines of text.

    A solid block would read as one tall vertical run (a page border), not writing.
    """
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(image)
    for y in range(y0, y1, 6):
        draw.rectangle([x0, y, x1 - 1, min(y + 2, y1 - 1)], fill=ink)
    return image


def write_fake_png_bytes(tmp_path: Path, name: str = "page.png") -> Path:
    """PNG magic + junk: enough for code that only base64-encodes the file."""
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return path


def write_recognition(path: Path, page: PageRecognition) -> Path:
    path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_run_pages(pages_dir: Path, *sizes: tuple[int, int]) -> list[Page]:
    """Blank page PNGs + ``pages.json`` (one page of 200x300 when no size is given)."""
    pages = [
        Page(page_number=n, image=f"page_{n:03d}.png", width=w, height=h)
        for n, (w, h) in enumerate(sizes or ((200, 300),), start=1)
    ]
    for page in pages:
        write_png(pages_dir / page.image, (page.width, page.height), (255, 255, 255))
    (pages_dir / "pages.json").write_text(
        json.dumps([page.model_dump(mode="json") for page in pages]), encoding="utf-8"
    )
    return pages


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
    kunci_dir: Path | None = None,
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
    if jawaban_dir is not None or kunci_dir is not None:
        lines.append("input:")
        if jawaban_dir is not None:
            lines.append(f"  jawaban_dir: {jawaban_dir.as_posix()}")
        if kunci_dir is not None:
            lines.append(f"  kunci_jawaban_dir: {kunci_dir.as_posix()}")
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


def single_question_json(question_number: int | str, relation: str) -> str:
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
    part_label: str = "",
) -> Question:
    """Question from LaTeX step strings (or explicit ``steps``); id follows ``number`` + ``part_label``."""
    student_steps = (
        steps
        if steps is not None
        else [make_step(i, text, raw_text=raw_text) for i, text in enumerate(latex, start=1)]
    )
    return Question(
        question_id=question_dir_name(number, part_label),
        question_number=number,
        part_label=part_label,
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
    part_label: str = "",
) -> QuestionValidation:
    """Steps numbered from 1; each spec is a status or ``(status, reason)``."""
    return QuestionValidation(
        question_number=number,
        question_id=question_dir_name(number, part_label),
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
    part_label: str = "",
) -> QuestionGrade:
    per = maximum / max(steps, 1)
    return QuestionGrade(
        question_id=question_dir_name(number, part_label),
        question_number=number,
        part_label=part_label,
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
    qdir = layout.questions_dir / question_dir_name(question.question_number, question.part_label)
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
