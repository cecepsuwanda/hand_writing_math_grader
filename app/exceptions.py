"""Domain errors for the math grader pipeline."""

from pathlib import Path


class MathGraderError(Exception):
    """Base error for recoverable CLI failures."""


class PdfNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"PDF not found: {path}")


class NoJawabanPdfError(MathGraderError):
    def __init__(self, jawaban_dir: Path) -> None:
        self.jawaban_dir = jawaban_dir
        super().__init__(
            f"No PDF files found in {jawaban_dir}. "
            "Place student answer PDFs under data/input/jawaban/."
        )


class InvalidPdfSelectionError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid PDF selection: {reason}")


class InvalidPdfError(MathGraderError):
    def __init__(self, path: Path, reason: str = "invalid or corrupt PDF") -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot open PDF '{path}': {reason}")


class EmptyPdfError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"PDF has no pages: {path}")


class PageRenderError(MathGraderError):
    def __init__(self, page_number: int, reason: str) -> None:
        self.page_number = page_number
        self.reason = reason
        super().__init__(f"Failed to render page {page_number}: {reason}")


class InvalidRenderSettingsError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class OllamaModelNotConfiguredError(MathGraderError):
    def __init__(self) -> None:
        super().__init__(
            "Vision model is not configured. Set ollama.vision_model in "
            "app/config/config.yaml or OLLAMA_VISION_MODEL in the environment."
        )


class OllamaUnavailableError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ollama is unavailable: {reason}")


class OllamaTimeoutError(MathGraderError):
    def __init__(self, model: str, timeout_seconds: float) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Ollama request timed out after {timeout_seconds}s (model={model})"
        )


class InvalidRecognitionJsonError(MathGraderError):
    def __init__(self, page_number: int, reason: str) -> None:
        self.page_number = page_number
        self.reason = reason
        super().__init__(
            f"Invalid recognition JSON for page {page_number}: {reason}"
        )


class RecognitionNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"No recognition JSON found in: {path}")


class RecognitionPathMismatchError(MathGraderError):
    def __init__(self, recognition_dir: Path, recognizer_output_dir: Path) -> None:
        self.recognition_dir = recognition_dir
        self.recognizer_output_dir = recognizer_output_dir
        super().__init__(
            "Recognition output directory mismatch: "
            f"controller={recognition_dir} recognizer={recognizer_output_dir}"
        )


class EmptyExtractionError(MathGraderError):
    def __init__(self, reason: str = "no questions found after extraction") -> None:
        self.reason = reason
        super().__init__(reason)


class QuestionsNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"No question.json artifacts found in: {path}")


class LatexBuildError(MathGraderError):
    def __init__(self, question_id: str, reason: str) -> None:
        self.question_id = question_id
        self.reason = reason
        super().__init__(f"Failed to build LaTeX for {question_id}: {reason}")


class MathParseError(MathGraderError):
    def __init__(self, expression: str, reason: str) -> None:
        self.expression = expression
        self.reason = reason
        super().__init__(f"Cannot parse math expression '{expression}': {reason}")


class ValidationWriteError(MathGraderError):
    def __init__(self, question_id: str, reason: str) -> None:
        self.question_id = question_id
        self.reason = reason
        super().__init__(f"Failed to write validation for {question_id}: {reason}")


class ValidationNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"validation.json not found at {path}. Run `python -m app.cli validate` first."
        )


class RubricNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Rubric not found: {path}")


class GradingError(MathGraderError):
    def __init__(self, question_id: str, reason: str) -> None:
        self.question_id = question_id
        self.reason = reason
        super().__init__(f"Failed to grade {question_id}: {reason}")


class GradingNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"No grading.json found in: {path}. Run `python -m app.cli grade` first."
        )


class ReportWriteError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Failed to write report: {reason}")
