# Konvensi Pengembangan

Aturan coding dan domain. Pipeline, lapisan, peta folder, dan kontrak CLI ada di [`architecture.md`](architecture.md); pemakaian di [`README.md`](../README.md).

## Prinsip arsitektur (wajib)

1. **MVC** — View (presentasi CLI), Controller (orkestrasi), Model/Services (domain + use-case). Lihat [`architecture.md`](architecture.md).
2. **SOLID** — abstraksi sempit di `app/interfaces/`, dependency injection, satu alasan berubah per modul.
3. **Clean code** — nama bermakna; fungsi kecil; konfigurasi terpusat; type hints + Pydantic; error eksplisit; komentar hanya untuk "mengapa".
4. **OOP + Functional Programming** berdampingan — OOP untuk service/client ber-state dan polymorphism; FP (fungsi di `app/functions/`) untuk transformasi deterministik.

## Domain matematika

Silabus, status per bab, dan topic pack: [`math-topics.md`](math-topics.md).

- MVP aktif: **topik 1.5 Pertidaksamaan** (pack `1.5`).
- Perluas domain **satu bab / pack per PR**, hanya setelah acceptance test bab sebelumnya hijau.
- Jangan mengklaim support bab yang belum punya pack + tes.

## Perluasan (Open/Closed)

- Bab/topik baru = **topic pack** baru di `app/topics/<id>/` (implementasi `TopicPack`) + entri di `_PACKS` (`app/topics/registry.py`). Inti pipeline tetap pack-agnostic.
- Notasi matematika baru = **capability** di `app/capabilities/registry.py` + fungsi `rewrite_*` di `app/functions/*_normalize.py`; pack memilihnya lewat `capability_ids`.
- Tahap/adapter baru = implementasi interface di `app/interfaces/`, di-wire di `app/services/pipeline_factory.py`.

## SOLID

- **S**: satu alasan berubah per kelas/modul.
- **O**: perluasan lewat interface/pack/capability baru, bukan edit besar inti.
- **L**: implementasi `VisionRecognizer` / `StepValidator` / `LlmClient` dapat diganti tanpa merusak pemanggil.
- **I**: interface sempit (`PdfRenderer`, `VisionRecognizer`, `CropWorkspace`, `StepValidator`, `LlmClient`, `QuestionLabeler`, `QuestionExtractorPort`, `QuestionGrader`, `LatexDocumentBuilder`, `KunciIngestPort`, `GradeReporter`, `DetailedReporter`, `MenuActions`, `TopicPack`, `Capability`).
- **D**: controller/service bergantung abstraksi; Ollama/PyMuPDF/SymPy diinjeksi lewat `pipeline_factory`.

## Clean coding

- Nama bermakna; fungsi kecil; tidak ada side effect tersembunyi.
- Konfigurasi terpusat (`app/config/config.yaml` + env `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL`, `OLLAMA_REASONING_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_RETRIES`); hindari magic string tersebar. **Jangan hard-code nama model.**
- Type hints; kontrak data antar layer dengan Pydantic.
- Komentar hanya untuk "mengapa".

## Error handling

- Error domain = subclass `MathGraderError` (`app/exceptions.py`) → CLI exit code `1` + box error. Exception lain → exit code `2`.
- Jangan menelan exception; ubah error library menjadi error domain di batas service.
- Kasus yang wajib ditangani: PDF korup / kosong, halaman gagal dirender, Ollama tidak berjalan / model tidak ada (4xx tidak di-retry), timeout, JSON model invalid, LaTeX invalid, parse SymPy gagal, confidence recognition rendah.
- Jika satu tahap gagal, **jangan hapus hasil tahap sebelumnya** dalam run yang sama.

## OOP dan Functional Programming

| Gunakan OOP | Gunakan fungsi modul |
|-------------|----------------------|
| Client/service ber-state (`OllamaClient`, `PyMuPdfRenderer`, `OllamaVisionRecognizer`) | Equivalence check, agregasi skor, mapping step→LaTeX, normalisasi notasi |
| Polymorphism lewat ABC/Protocol | Filter/map tahap pipeline tanpa mutasi input |
| Domain model (Pydantic) | Helper di `app/functions/` |

- `app/functions/` utamanya pure. Pengecualian yang disengaja: helper baca/tulis **artefak** (`*_artifact.py`, `question_crops.py`, `image_crop.py`, `report_details.py`, `workspace_reset.py`, `load_exam_schema`). Jangan menambah I/O jaringan atau model di sana.
- Composition over inheritance; jangan buat class berisi static method saja.

## Recognition fidelity

Recognition memakai **ink bbox**: clustering tinta deterministik (`ink_layout`), lalu crop Pillow + konfirmasi user (`page_*_regions.json` editable) + `crop_math`. Konteks ujian ke vision hanya **stem + `expects_figure`** dari `exam_schema` — jangan kirim steps/HP ke OCR.

Saat recognition, LLM **tidak boleh**:

- memperbaiki persamaan atau typo;
- menyimpulkan langkah yang tidak tertulis;
- mengganti jawaban dengan yang dianggap benar;
- menyalin solusi dari kunci.

Jika ragu: tandai `uncertain` / confidence rendah / `review_required`, dan pertahankan gambar asli + crops.

## Validasi dan grading

1. Syntax / parse (symbolic ASCII / LaTeX artefak).
2. SymPy: konsistensi langkah mahasiswa.
3. LLM judge hanya untuk langkah yang SymPy tandai `uncertain`.
4. **Grading:** skor langkah = konsistensi; soft-align ke `exam_schema` / solutions `.tex` = audit; skor `final_answer` = min(konsistensi, standard SymPy).
5. Partial credit; jangan nolkan semua skor hanya karena final answer salah.
6. Error type deterministik: `calculation` / `carry_forward` / `transcription` / `uncertain`; `conceptual` hanya dari annotator LLM (feedback, tidak mengubah skor).

Output LLM divalidasi terhadap schema Pydantic. Status `uncertain` dan `REVIEW_REQUIRED` diizinkan.

### Jejak audit

Setiap skor harus dapat ditelusuri dari artefak run: soal + stem (`question_crops/`), langkah mahasiswa + page reference (`question.json`), status per langkah + metode SymPy/LLM + alasan (`validation.json`), skor langkah, error type, feedback, skor final vs standar (`grading.json`), serta model dan versi prompt (`report.json` metadata).

## Kunci jawaban (ingest)

`python -m app.cli ingest-kunci` mem-parse `data/input/kunci_jawaban/*.tex` menjadi `exam_schema.json` (termasuk `topic_id`), `solutions/question_NNN.tex`, dan `rubrics/question_NNN.json`.

Kontrak markup itemize di dalam `\textbf{Penyelesaian}` (pack `1.5`):

| Item | Hasil schema |
|------|----------------|
| `Langkah-langkah…` | `steps` (shared algebra) |
| `Metode N: Label` | `methods[]` (`id` slug, mis. Pemaktoran→`factoring`, Rumus ABC→`quadratic_formula`) |
| `Tentukan Titik Kritis` / `Titik Potong` | milestone + part `critical_points` |
| `Analisis Tanda` | milestone + part `sign_chart` |
| `Gambar Garis Bilangan…` / tikzpicture | `expects_figure` + part `figure` + `number_line` (dari HP) |
| `HP: $…$` | `final` + milestone `hp` |

**Skor per bucket rubrik:** `algebra` = konsistensi langkah saja (soft-align best-method = audit). Bucket `critical_points` / `figure` di-score terpisah; `final_answer` = min(konsistensi, standard SymPy). Skor `figure` = set-equivalence `number_line` (endpoint open/closed + daerah arsir / union) vs gambar mahasiswa (`FigureRef.symbolic.repr` / caption); schema lama tanpa `number_line` → presence. Recognition (`app/prompts/crop_math.txt`) mengisi `role` per langkah (`algebra` / `critical_points` / `sign_chart` / `figure` / `hp`); figure step memakai `NUMBER_LINE(...)` di `symbolic.repr`.

## Reproducibility dan keamanan

- Tersimpan saat ini: `report.json` metadata = `generated_at`, `student_id`, `standard_dir`, model vision/reasoning, versi prompt (recognition dari header `crop_math.txt`, `validation-v1`, `grading-v1`).
- Target (belum ada): versi aplikasi dan `submission_id`.
- Jangan commit password/API key; pakai environment variable.
- Prefer Ollama **lokal** untuk data mahasiswa. Model `*-cloud` di `config.yaml` berarti gambar keluar dari mesin.

## Logging

Modul memakai `logging.getLogger(__name__)` (model, attempt, status HTTP, durasi, status tahap). CLI belum mengonfigurasi handler, jadi log INFO/DEBUG tidak tampil secara default. Pengecualian: pada exit code `2`, `_report_failure` di `app/cli.py` memanggil `logger.exception`, sehingga traceback tetap tercetak ke stderr lewat `logging.lastResort` (level WARNING ke atas). Target: timestamp, `submission_id`, page, model, prompt_version, processing_time.

## Testing

Pytest tanpa file `test_*.py` baru: perluas lewat `class Test*` + method `test_*` di inventaris `tests/`. Setup bersama di `tests/support/` (`builders.py`, `fakes.py`, `harness.py`, `asserts.py`). Detail: [`testing.md`](testing.md).

## Referensi implementasi

Sumber ide dan pembanding, bukan kewajiban dipakai:

- Math-grading: https://github.com/anishstoppo55/Math-grading
- VLM-Math: https://github.com/shreemitra/VLM-Math
- GradeMate: https://github.com/luisfilipeap/GradeMate
- Autograding handwritten mathematical worksheets: https://github.com/divyaprabha123/Autograding-handwritten-mathematical-worksheets
- ExamGrader: https://github.com/CCU-Bioinformatics-Lab/ExamGrader
- EvalAI: https://github.com/EvalAiProject/evalai
- PaddleOCR formula recognition: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/formula_recognition.en.md
