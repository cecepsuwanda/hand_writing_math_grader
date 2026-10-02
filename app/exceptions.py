"""Domain errors for the math grader pipeline."""

from pathlib import Path


class MathGraderError(Exception):
    """Base error for recoverable CLI failures."""


class ConfigNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"Config file not found: {path}. Periksa path --config "
            "(letakkan sebelum subcommand) atau hapus opsi itu untuk memakai default."
        )


class PdfNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"PDF not found: {path}")


class KunciNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Kunci .tex not found: {path}")


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


class NoKunciTexError(MathGraderError):
    def __init__(self, kunci_dir: Path) -> None:
        self.kunci_dir = kunci_dir
        super().__init__(
            f"No .tex files found in {kunci_dir}. "
            "Place kunci jawaban under data/input/kunci_jawaban/."
        )


class AmbiguousKunciDirError(MathGraderError):
    def __init__(self, kunci_dir: Path, names: list[str]) -> None:
        self.kunci_dir = kunci_dir
        self.names = list(names)
        super().__init__(
            f"{len(self.names)} kunci .tex files in {kunci_dir} "
            f"({', '.join(self.names)}); one ingest = one kunci per topic. "
            "Pass the file explicitly: ingest-kunci <file.tex> [--topic <id>]."
        )


class InvalidKunciSelectionError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid kunci selection: {reason}")


class RunNotSpecifiedError(MathGraderError):
    def __init__(
        self, output_root: Path, available: list[str], *, hint: str | None = None
    ) -> None:
        self.output_root = output_root
        self.available = list(available)
        if self.available:
            runs = "Available runs: " + ", ".join(self.available) + "."
        else:
            runs = "No run folders yet; process a PDF first."
        advice = hint if hint is not None else "Pass --run <nama_pdf>."
        super().__init__(
            f"Cannot pick a run folder under {output_root}. {advice} {runs}"
        )


class InvalidRunSelectionError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid run selection: {reason}")


class NoRegionsForLabelingError(MathGraderError):
    def __init__(self, crops_dir: Path) -> None:
        self.crops_dir = crops_dir
        super().__init__(
            f"No page_*_regions.json under {crops_dir}. "
            "Run crop ink (menu 3) before recognizing question numbers."
        )


class PageImageMissingError(MathGraderError):
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        super().__init__(
            f"Page image missing for recrop: {image_path}. "
            "Run crop ink (menu 3 / propose-crops) to render pages first."
        )


class CropsRegionsMissingError(MathGraderError):
    def __init__(self, crops_dir: Path) -> None:
        self.crops_dir = crops_dir
        super().__init__(
            f"No page_*_regions.json under {crops_dir}. "
            "Run menu 3 (crop ink) or 4 (recrop) first."
        )


class NoRegionsJsonError(MathGraderError):
    def __init__(self, crops_dir: Path) -> None:
        self.crops_dir = crops_dir
        super().__init__(f"No regions JSON found under {crops_dir}; cannot recrop.")


class RegionsArtifactMissingError(MathGraderError):
    def __init__(self, json_path: Path) -> None:
        self.json_path = json_path
        super().__init__(f"Regions JSON not found: {json_path}")


class EmptyRegionsError(MathGraderError):
    def __init__(self, json_path: Path) -> None:
        self.json_path = json_path
        super().__init__(f"No regions in {json_path}; add at least one box or re-run crop ink.")


class StandardDirMismatchError(MathGraderError):
    def __init__(self, requested: Path, injected: Path) -> None:
        self.requested = requested
        self.injected = injected
        super().__init__(
            f"standard_dir {requested} does not match injected "
            f"KunciIngester dir {injected}"
        )


class InteractiveTerminalRequiredError(MathGraderError):
    def __init__(self) -> None:
        super().__init__(
            "Interactive menu requires a terminal. "
            "Use `process`, `propose-crops`, `recrop`, `ingest-kunci`, "
            "or other subcommands instead."
        )


class ExamSchemaMissingError(MathGraderError):
    def __init__(self, standard_dir: Path) -> None:
        self.standard_dir = standard_dir
        super().__init__(
            f"exam_schema.json not found under {standard_dir}. "
            "Ingest kunci jawaban first (menu 2 / ingest-kunci) so the question "
            "count is known."
        )


class QuestionCropsInvalidError(MathGraderError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        detail = "; ".join(self.errors)
        super().__init__(
            f"question_crops tidak valid: {detail}. "
            "Perbaiki crops/question_crops/question_*.json lalu jalankan menu 6 "
            "(relabel-questions), atau kenali ulang lewat menu 5 (label-questions)."
        )


class QuestionArtifactsInvalidError(MathGraderError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        detail = "; ".join(self.errors)
        super().__init__(
            f"question.json tidak valid: {detail}. "
            "Perbaiki questions/question_*/question.json lalu lanjutkan lewat menu 8 "
            "(finish-questions), atau kenali ulang lewat menu 7."
        )


class QuestionCropsNotFoundError(MathGraderError):
    def __init__(self, json_dir: Path) -> None:
        self.json_dir = json_dir
        super().__init__(f"{json_dir} belum ada; jalankan label-questions dulu")


class OperationCancelledError(MathGraderError):
    def __init__(self, step: str = "") -> None:
        self.step = step
        where = f" ({step})" if step else ""
        super().__init__(f"Dibatalkan oleh pengguna{where} (Ctrl+C).")


class InvalidMenuSelectionError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid menu selection: {reason}")


class UnknownTopicError(MathGraderError):
    def __init__(self, topic_id: str, known: list[str] | tuple[str, ...] = ()) -> None:
        self.topic_id = topic_id
        self.known = list(known)
        known_txt = ", ".join(self.known) if self.known else "(none registered)"
        super().__init__(
            f"Unknown topic pack '{topic_id}'. Known packs: {known_txt}."
        )


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


class OllamaRequestError(OllamaUnavailableError):
    """Ollama rejected the request (4xx); retrying cannot help."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        super().__init__(f"request failed {status_code}: {body}")


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


class ReportPdfError(MathGraderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            f"report.pdf tidak dikompilasi: {reason}. "
            "report.tex tetap ada; kompilasi ulang lewat menu 8 atau subcommand `report`."
        )
