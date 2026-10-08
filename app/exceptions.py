"""Domain errors for the math grader pipeline."""

from pathlib import Path


class MathGraderError(Exception):
    """Base error for recoverable pipeline failures (shown as a flash in the web UI)."""


class ConfigNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"Config file not found: {path}. Periksa path --config "
            "atau hapus opsi itu untuk memakai app/config/config.yaml."
        )


class ConfigInvalidError(MathGraderError):
    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"Config tidak valid ({source}): {detail}")


class UnsafeOutputDirError(MathGraderError):
    def __init__(self, label: str, path: Path, run_root: Path, reason: str) -> None:
        self.label = label
        self.path = path
        self.run_root = run_root
        super().__init__(
            f"Folder {label} tidak boleh dikosongkan: {path}\n"
            f"{reason} (folder run: {run_root}).\n"
            "Kosongkan folder itu secara manual, pakai folder kosong, "
            "atau hapus opsi path agar memakai folder default di dalam run."
        )


class PdfNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"PDF not found: {path}")


class KunciNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Kunci .tex not found: {path}")




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
            "Pilih satu file .tex di halaman awal lalu klik Ingest."
        )





class NoRegionsForLabelingError(MathGraderError):
    def __init__(self, crops_dir: Path) -> None:
        self.crops_dir = crops_dir
        super().__init__(
            f"No page_*_regions.json under {crops_dir}. "
            "Jalankan Propose crops dulu sebelum mengenali nomor soal."
        )


class PageImageMissingError(MathGraderError):
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        super().__init__(
            f"Page image missing for recrop: {image_path}. "
            "Jalankan Propose crops dulu untuk merender halaman."
        )


class CropsRegionsMissingError(MathGraderError):
    def __init__(self, crops_dir: Path) -> None:
        self.crops_dir = crops_dir
        super().__init__(
            f"No page_*_regions.json under {crops_dir}. "
            "Jalankan Propose crops atau simpan kotak di editor crop dulu."
        )



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



class ExamSchemaMissingError(MathGraderError):
    def __init__(self, standard_dir: Path) -> None:
        self.standard_dir = standard_dir
        super().__init__(
            f"exam_schema.json not found under {standard_dir}. "
            "Ingest kunci jawaban dulu di halaman awal agar jumlah soal diketahui."
        )


class QuestionCropsInvalidError(MathGraderError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        detail = "; ".join(self.errors)
        super().__init__(
            f"question_crops tidak valid: {detail}. "
            "Perbaiki nomor soal di halaman Label, atau kenali ulang lewat tombol "
            "Deteksi otomatis (vision)."
        )


class QuestionArtifactsInvalidError(MathGraderError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        detail = "; ".join(self.errors)
        super().__init__(
            f"question.json tidak valid: {detail}. "
            "Perbaiki di halaman Review lalu klik Nilai sekarang, atau transkripsi ulang "
            "dari halaman run (Transkripsi lalu review)."
        )


class QuestionCropsNotFoundError(MathGraderError):
    def __init__(self, json_dir: Path) -> None:
        self.json_dir = json_dir
        super().__init__(f"{json_dir} belum ada; kenali nomor soal di halaman Label dulu")




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
            f"validation.json not found at {path}. Jalankan Nilai sekarang di halaman Review."
        )


class ValidationStaleError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"validation.json at {path} is older than question.json (student work changed). "
            "Jalankan Nilai sekarang di halaman Review lagi."
        )


class RubricNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Rubric not found: {path}")


class RubricInvalidError(RubricNotFoundError):
    """Rubric file exists but is unreadable or inconsistent (skipped like a missing one)."""

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        Exception.__init__(self, f"Rubric invalid: {path}: {detail}")


class GradingError(MathGraderError):
    def __init__(self, question_id: str, reason: str) -> None:
        self.question_id = question_id
        self.reason = reason
        super().__init__(f"Failed to grade {question_id}: {reason}")


class GradingNotFoundError(MathGraderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"No grading.json found in: {path}. Jalankan Nilai sekarang di halaman Review."
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
            "report.tex tetap ada; kompilasi ulang dengan Nilai sekarang di halaman Review."
        )


class RunNotFoundError(MathGraderError):
    def __init__(self, run_name: str) -> None:
        self.run_name = run_name
        super().__init__(
            f"Run '{run_name}' tidak ditemukan. Pilih PDF di halaman awal lalu "
            "jalankan Propose crops untuk membuat folder run."
        )


class ArtifactNotFoundError(MathGraderError):
    def __init__(self, description: str) -> None:
        self.description = description
        super().__init__(f"Artefak tidak ditemukan: {description}")


class UnsafeArtifactPathError(MathGraderError):
    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(f"Path artefak tidak diizinkan: {raw!r}")


class UploadRejectedError(MathGraderError):
    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"Upload '{filename}' ditolak: {reason}")


class InvalidRegionsError(MathGraderError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("Kotak crop tidak valid: " + "; ".join(self.errors))


class JobNotFoundError(MathGraderError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Job '{job_id}' tidak ditemukan (server mungkin sudah dimulai ulang).")


class JobAlreadyRunningError(MathGraderError):
    def __init__(self, run_name: str, job_id: str) -> None:
        self.run_name = run_name
        self.job_id = job_id
        super().__init__(
            f"Run '{run_name}' masih punya job aktif ({job_id}); tunggu sampai selesai."
        )
