from app.controllers.ingest_kunci_controller import IngestKunciResult
from app.models.grading import GradeResult
from app.models.latex import LatexResult
from app.models.page import RenderResult
from app.models.question import ExtractResult
from app.models.recognition import RecognizeResult
from app.models.report import ReportResult
from app.models.validation import ValidateResult
from app.views.style import bold, dim, green


def _ok(title: str) -> None:
    print(green(bold(f"✓ {title}")))


def print_render_result(result: RenderResult) -> None:
    page_count = len(result.pages)
    _ok(f"Rendered {page_count} page(s) → {result.output_dir}")
    for page in result.pages:
        print(f"  {page.image} ({page.width}x{page.height})")
    print(dim(f"  Metadata: {result.metadata_path}"))


def print_recognize_result(result: RecognizeResult) -> None:
    page_count = len(result.pages)
    _ok(f"Recognized {page_count} page(s) → {result.output_dir}")
    for page, artifact in zip(result.pages, result.artifact_paths, strict=False):
        question_count = len(page.questions)
        step_count = sum(len(q.steps) for q in page.questions)
        print(
            f"  page {page.page_number}: {question_count} question(s), "
            f"{step_count} step(s) → {artifact.name}"
        )
        print(dim(f"    model={page.model or '(unset)'} prompt={page.prompt_version}"))


def print_extract_result(result: ExtractResult) -> None:
    _ok(f"Extracted {len(result.questions)} question(s) → {result.output_dir}")
    for question, artifact in zip(result.questions, result.artifact_paths, strict=False):
        print(
            f"  {question.question_id}: {len(question.student_steps)} step(s), "
            f"pages={question.page_references}, "
            f"status={question.segmentation_status.value} → {artifact}"
        )
        if question.student_final_answer:
            print(dim(f"    final_answer: {question.student_final_answer}"))
        if question.figure_refs:
            with_nl = sum(
                1
                for fig in question.figure_refs
                if fig.symbolic is not None and (fig.symbolic.repr or "").strip()
            )
            print(
                dim(
                    f"    figures: {len(question.figure_refs)} "
                    f"({with_nl} with NUMBER_LINE symbolic)"
                )
            )


def print_latex_result(result: LatexResult) -> None:
    _ok(f"Built {len(result.artifacts)} student.tex file(s) → {result.questions_dir}")
    for artifact in result.artifacts:
        print(f"  {artifact.question_id} → {artifact.path}")


def print_validate_result(result: ValidateResult) -> None:
    _ok(f"Validated {len(result.validations)} question(s) → {result.questions_dir}")
    for validation, artifact in zip(
        result.validations, result.artifact_paths, strict=False
    ):
        statuses = ", ".join(
            f"s{step.step_number}={step.status.value}" for step in validation.steps
        )
        print(f"  {validation.question_id}: {statuses} → {artifact}")
        if validation.final_answer_status is not None:
            print(
                dim(f"    final_answer={validation.final_answer_status.status.value}")
            )


def print_grade_result(result: GradeResult) -> None:
    _ok(
        f"Graded {len(result.grades)} question(s) "
        f"(standard={result.standard_dir}) → {result.questions_dir}"
    )
    for grade, artifact in zip(result.grades, result.artifact_paths, strict=False):
        print(
            f"  {grade.question_id}: {grade.score}/{grade.maximum_score} "
            f"{grade.review_status.value} → {artifact}"
        )
        if grade.part_statuses:
            parts = ",".join(
                f"{part_id}:{status}"
                for part_id, status in sorted(grade.part_statuses.items())
            )
            print(dim(f"    parts={parts}"))


def print_ingest_kunci_result(result: IngestKunciResult) -> None:
    _ok(
        f"Ingested {len(result.written)} artifact(s) from {result.source} "
        f"→ {result.standard_dir}"
    )
    if result.schema_path is not None:
        _ok(f"Exam schema: {result.schema_path}")
    for path in result.written:
        print(f"  {path}")


def print_report_result(result: ReportResult) -> None:
    exam = result.exam_report
    _ok(
        f"Report for {exam.metadata.student_id}: "
        f"{exam.total_score}/{exam.maximum_total} {exam.overall_status.value} "
        f"→ {result.output_dir}"
    )
    print(f"  JSON: {result.report_json_path}")
    print(f"  CSV:  {result.summary_csv_path}")
    print(f"  HTML: {result.report_html_path}")
