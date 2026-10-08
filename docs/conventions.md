# Konvensi Pengembangan

Aturan coding dan domain. Pipeline, lapisan, peta folder, dan kontrak web ada di [`architecture.md`](architecture.md); pemakaian di [`README.md`](../README.md).

## Prinsip arsitektur (wajib)

1. **MVC** — View (template Jinja2 + HTMX/Alpine), Controller (router tipis + orkestrasi), Model/Services (domain + use-case). Lihat [`architecture.md`](architecture.md).
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
- **I**: interface sempit (`PdfRenderer`, `VisionRecognizer`, `CropWorkspace`, `StepValidator`, `LlmClient`, `QuestionLabeler`, `QuestionExtractorPort`, `QuestionGrader`, `LatexDocumentBuilder`, `KunciIngestPort`, `GradeReporter`, `DetailedReporter`, `LatexCompiler`, `TopicPack`, `Capability`).
- **D**: controller/service bergantung abstraksi; Ollama/PyMuPDF/SymPy diinjeksi lewat `pipeline_factory`.

## Clean coding

- Nama bermakna; fungsi kecil; tidak ada side effect tersembunyi.
- Konfigurasi terpusat (`app/config/config.yaml` + env `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL`, `OLLAMA_REASONING_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_RETRIES`); hindari magic string tersebar. **Jangan hard-code nama model.**
- Type hints; kontrak data antar layer dengan Pydantic.
- Komentar hanya untuk "mengapa".

## Error handling

- Error domain = subclass `MathGraderError` (`app/exceptions.py`) → status 4xx + pesan domain (flash HTMX, halaman error, atau JSON `{"detail"}` di `/api/*`); di job → status "Gagal" dengan pesan itu. Exception lain di job → di-log dengan traceback dan job gagal; di route → 500.
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
- Proses eksternal (`subprocess`) hanya ada di `services/latex/pdflatex_compiler.py`, lewat `runner` yang di-inject (tes memakai `FakeLatexRunner`, tidak pernah pdflatex sungguhan). Path pdflatex diambil dari `config.report.pdf` / env `PDFLATEX_PATH`, atau dideteksi otomatis; jangan di-hard-code di tempat lain. Kegagalan kompilasi PDF (`ReportPdfError`) tidak menggagalkan run.
- `raw_text` OCR hanya disanitasi saat dirender ke `report.tex` (`app/functions/latex_report.py`); `question.json` tidak diubah. Escape literal `\n`/`\r`/`\t` diganti `\quad`, dan perintah di luar allowlist `_MATH_COMMANDS` jatuh ke `\texttt`, sehingga makro yang tidak dikenal tidak sampai ke pdflatex.
- Composition over inheritance; jangan buat class berisi static method saja.

## Recognition fidelity

Recognition memakai **ink bbox**: clustering tinta deterministik (`ink_layout`), lalu crop Pillow + konfirmasi user (`page_*_regions.json` editable) + `crop_math`. Konteks ujian ke vision hanya **stem + `expects_figure`** dari `exam_schema` — jangan kirim steps/HP ke OCR.

Koreksi transkripsi hanya oleh **user**, di checkpoint tinjau `question.json` setelah Extract (`QuestionReviewController`); sistem cuma memberi tanda (`ReviewFlag`) dan tidak pernah mengubah langkah sendiri. Penanda harus pack-agnostic: cek `symbolic.kind`, bukan nama role.

Saat recognition, LLM **tidak boleh**:

- memperbaiki persamaan atau typo;
- menyimpulkan langkah yang tidak tertulis;
- mengganti jawaban dengan yang dianggap benar;
- menyalin solusi dari kunci.

Jika ragu: tandai `uncertain` / confidence rendah / `review_required`, dan pertahankan gambar asli + crops.

## Validasi dan grading

1. Syntax / parse (symbolic ASCII / LaTeX artefak).
2. SymPy: konsistensi langkah mahasiswa. Setiap langkah dicek terhadap **langkah acuan** = langkah `TRANSITION` terakhir sebelumnya, bukan otomatis langkah sebelumnya. Pack memetakan `role` → `StepCheck` (`TopicPack.step_checks`): `transition` (ekuivalen dengan acuan), `zero_makers` (nilai = pembuat nol pembilang/penyebut acuan), `numeric_eval` (aritmetika uji titik benar), `solution_set` (himpunan solusi = acuan), `not_symbolic` (figure → `uncertain`). Role tanpa pemetaan = `transition`. Final answer dibandingkan dengan acuan terakhir bila ada langkah non-`transition`, selain itu dengan langkah terakhir. Reason di `validation.json` diawali jenis ceknya (mis. `zero_makers: …`).
3. LLM judge hanya untuk langkah yang SymPy tandai `uncertain`; judge menerima langkah acuan (bukan langkah sebelumnya) dan jenis ceknya (`Check kind: …`).
4. **Grading:** skor langkah = konsistensi; soft-align ke `exam_schema` / solutions `.tex` = audit; skor `final_answer` = min(konsistensi, standard SymPy).
5. Partial credit; jangan nolkan semua skor hanya karena final answer salah.
6. Error type deterministik: `calculation` / `carry_forward` / `transcription` / `uncertain`; `conceptual` hanya dari annotator LLM (feedback, tidak mengubah skor).

Output LLM divalidasi terhadap schema Pydantic. Status `uncertain` dan `REVIEW_REQUIRED` diizinkan.

### Jejak audit

Setiap skor harus dapat ditelusuri dari artefak run: soal + stem (`question_crops/`), langkah mahasiswa + page reference (`question.json`), status per langkah + metode SymPy/LLM + alasan (`validation.json`), skor langkah, error type, feedback, skor final vs standar (`grading.json`), serta model dan versi prompt (`report.json` metadata).

## Kunci jawaban (ingest)

Tombol **Ingest** di halaman awal (`POST /kunci/ingest`) mem-parse satu file `data/input/kunci_jawaban/*.tex` menjadi `exam_schema.json` (termasuk `topic_id`), `solutions/question_NNN.tex`, dan `rubrics/question_NNN.json`.

Kontrak markup itemize di dalam `\textbf{Penyelesaian}` (pack `1.5`):

| Item | Hasil schema |
|------|----------------|
| `Langkah-langkah…` | `steps` (shared algebra) |
| `Metode N: Label` | `methods[]` (`id` slug, mis. Pemaktoran→`factoring`, Rumus ABC→`quadratic_formula`) |
| `Tentukan Titik Kritis` / `Titik Potong` | milestone + part `critical_points` |
| `Analisis Tanda` | milestone + part `sign_chart` |
| `Gambar Garis Bilangan…` / tikzpicture | `expects_figure` + part `figure` + `number_line` (dari HP) |
| `HP: $…$` | `final` + milestone `hp` |

**Skor per bucket rubrik:** `algebra` = konsistensi langkah saja (soft-align best-method = audit). Bucket `critical_points` / `sign_chart` / `figure` di-score terpisah; `final_answer` = min(konsistensi, standard SymPy). Skor `figure` = set-equivalence `number_line` (endpoint open/closed + daerah arsir / union) vs gambar mahasiswa (`FigureRef.symbolic.repr` / caption); schema lama tanpa `number_line` → presence. Recognition (`app/prompts/crop_math.txt`) mengisi `role` per langkah (`algebra` / `critical_points` / `sign_chart` / `figure` / `hp`); figure step memakai `NUMBER_LINE(...)` di `symbolic.repr`.

**Pemisahan `sign_chart`.** `role_rubric_parts` memetakan role → daftar kandidat bucket rubrik, kandidat pertama yang ada di rubrik yang dipakai (`fold_role_marks`). `sign_chart` memilih bucket `sign_chart` sendiri bila rubrik memilikinya (kunci dengan dua milestone → `critical_points` 1.0 + `sign_chart` 1.0; kunci dengan `sign_chart` saja → 2.0), sehingga akar yang benar tidak tertahan tabel tanda. Rubrik lama yang hanya punya `critical_points` membuat kedua role jatuh ke bucket itu lagi dan dirata-ratakan seperti sebelumnya — skornya identik, jadi ingest kunci ulang tidak wajib (tapi perlu agar baris `sign_chart` muncul di laporan).

**HP yang cocok kunci tidak di-nol-kan.** Bila `compare()` bilang jawaban akhir cocok dengan kunci tetapi rantai langkah mahasiswa tidak konsisten, skor diambil dari kunci (bukan `min(...)` yang men-nol-kan) dan barisnya ditandai review. Feedback baris itu diakhiri penanda mesin `; standard: …`, `; scored under part:…`, dan `; key override: …` (`split_feedback_markers`); `FeedbackAnnotator` menulis ulang hanya bagian manusianya dan menempelkan penanda kembali apa adanya, serta melewati baris ber-`key override` supaya catatan keputusannya tidak terhapus.

## Reproducibility dan keamanan

- Tersimpan saat ini: `report.json` metadata = `generated_at`, `student_id`, `standard_dir`, model vision/reasoning, versi prompt (recognition dari header `crop_math.txt`, `validation-v2`, `grading-v1`).
- Target (belum ada): versi aplikasi dan `submission_id`.
- Jangan commit password/API key; pakai environment variable.
- Prefer Ollama **lokal** untuk data mahasiswa. Model `*-cloud` di `config.yaml` berarti gambar keluar dari mesin.

## Logging

Modul memakai `logging.getLogger(__name__)` (model, attempt, status HTTP, durasi, status tahap). `python -m app.web` memasang `logging.basicConfig(level=INFO)`, jadi log tampil di konsol server. Controller tidak mencetak ke stdout: peringatan (rubric hilang, PDF gagal dikompilasi, soal tidak dinilai) lewat `logger.warning`; pesan yang perlu dilihat user dikirim ke progress job (`JobReporter.message`) atau flash halaman. Error tak terduga di job tercatat dengan `logger.exception` dan pesannya tampil sebagai "Gagal: …" di halaman job. Target: timestamp, `submission_id`, page, model, prompt_version, processing_time.

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
