"""Deterministic question artifact names."""


def question_dir_name(question_number: int) -> str:
    if question_number < 1:
        raise ValueError(f"question_number must be >= 1, got {question_number}")
    return f"question_{question_number:03d}"


def question_artifact_filename() -> str:
    return "question.json"


def student_tex_filename() -> str:
    return "student.tex"


def latex_source_filename() -> str:
    """Sidecar from recognition latex_document (not stored in question.json)."""
    return "latex_source.tex"


def validation_filename() -> str:
    return "validation.json"


def grading_filename() -> str:
    return "grading.json"


def report_json_filename() -> str:
    return "report.json"


def summary_csv_filename() -> str:
    return "summary.csv"


def report_html_filename() -> str:
    return "report.html"
