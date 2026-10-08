# Arsitektur

## Prinsip wajib

Proyek ini wajib memakai **MVC**, **SOLID**, **clean code**, serta **OOP** berdampingan dengan **functional programming**. Aturan coding dan domain: [`conventions.md`](conventions.md). Pemakaian web UI: [README root](../README.md).

## Pipeline

```text
PDF → page images
  → ink-cluster bboxes (deterministik; Pillow)
  → tulis page_NNN_regions.json (editable) + crop Pillow
  → editor crop web (gambar/geser/ubah ukuran/hapus kotak; simpan = crop ulang, padding 0)
  → [opsional] crop_label VLM → crops/question_crops/question_NNN.json
    → halaman Label: koreksi nomor soal per crop lalu simpan
  → crop_math VLM (nomor soal dari question_crops bila ada) → symbolic JSON (+ latex_source.tex)
  → gabung per soal → questions/question_NNN/question.json
    → halaman Review: edit langkah (preview KaTeX), simpan per soal, lalu "Nilai sekarang"
  → student.tex → validasi SymPy (± LLM) → grading → report
  → pdflatex report.tex → report.pdf (gagal = peringatan saja)
```

**Tinjau `question.json`.** Job *Transkripsi lalu review* (`ProcessController.transcribe_from_crops`) berhenti setelah Extract. Halaman Review menampilkan `QuestionReviewController.collect`: per langkah (`role`, `raw_text`, `symbolic.repr`) beserta tanda `low_confidence` (< `recognition.review_min_confidence`), `uncertain_mark` (`[uncertain` di `raw_text`), dan `missing_symbolic` (`repr` kosong, kecuali `kind: figure`). Penanda dihitung pure di `functions/question_review.py`; baca, tulis, dan penghapusan sidecar ada di `functions/question_review_artifact.py`. Simpan satu soal (`PUT /api/runs/<run>/questions/<id>` → `save_question`) memvalidasi lewat Pydantic, menulis `question.json`, dan menghapus `latex_source.tex` soal itu agar `student.tex` dibangun ulang dari langkah hasil edit. Di dalam pipeline, `_run_from_questions` memanggil `require_valid`: JSON yang tidak terbaca atau `question_id` yang tidak sama dengan nama folder menghentikan run (`QuestionArtifactsInvalidError`) sebelum LaTeX. Tahap ini bukan `ProcessStage` tersendiri; progres tetap 7 tahap.

**Lanjut dari `question.json` yang sudah diedit (tombol "Nilai sekarang", `POST /runs/<run>/finish-questions`).** `ProcessController.process_from_questions` berbagi ekor pipeline (`_run_from_questions`: tinjau → LaTeX → validasi → grading → report) dengan `process` dan `process_from_crops`, tetapi tidak menjalankan recognize/extract dan tidak mengosongkan `questions/`, jadi `question.json` hanya dibaca. Sebelum tinjau, `QuestionReviewController.prune_stale_latex_sources` menghapus `latex_source.tex` yang lebih lama (mtime) dari `question.json`-nya. Aturan ini aman karena Extract menulis `question.json` lebih dulu. Folder tanpa `question.json` → `QuestionsNotFoundError`. Progres dimulai dari LATEX (4/7), dan tahap ini tidak butuh model vision.

Recognition dan grading **dipisah**. JSON soal menyimpan `raw_text` + `symbolic` (bukan LaTeX). LaTeX hanya di artefak `.tex`. Satu crop boleh menghasilkan beberapa soal bila ink menggabungkan jawaban dan model mengembalikan `{"questions":[...]}`.

**Nomor soal per crop (`question_crops/`).** Format file dan alur user: [README root](../README.md#nomor-soal-question_crops). Aturan internal: *Deteksi otomatis (vision)* (`label_all`) menulis satu file per soal di kunci; crop tanpa label mewarisi soal sebelumnya dalam urutan baca (halaman, lalu `order`). Form halaman Label (`save_mapping` → `reload_all`) memvalidasi: soal di luar kunci atau nama crop tak dikenal = error; soal tanpa crop atau crop tanpa soal = peringatan. Saat recognition, satu nomor yang ditetapkan user dipaksakan, beberapa nomor membatasi pilihan model, dan soal yang tersebar di beberapa crop tidak di-demote sebagai duplikat. File yang tidak valid menghentikan run (`QuestionCropsInvalidError`); folder yang belum ada hanya memicu peringatan.

`exam_schema.json`: recognition (crop_math dan crop_label) hanya menerima **stem + flag `expects_figure`**; `steps` / `final` / `HP` / `number_line` / `parts` hanya untuk grading.

Aturan validasi dan grading: [`conventions.md`](conventions.md#validasi-dan-grading).

## Lapisan MVC

```text
View (web)          → Jinja2 templates + HTMX partials + Alpine/Konva/KaTeX (app/web/templates, static)
Controller          → routers FastAPI tipis (app/web/routers) → WebPipeline → controller use-case
Model + Services    → domain, use-case, pure functions, ports
Infrastructure      → Ollama, PyMuPDF, SymPy, filesystem, config
```

**Arah ketergantungan:** View → Controller → Services/Models → Infrastructure.

| Layer | Boleh | Tidak boleh |
|-------|--------|-------------|
| View (template/JS) | Render model yang sudah jadi; JS hanya interaksi (gambar kotak, edit langkah) dan memanggil route JSON | Logika domain; akses filesystem selain lewat route |
| Router (`app/web/routers`) | Parse request (Pydantic `app/web/schemas.py`), panggil `WebPipeline` / `JobManager`, pilih template / JSON | Logika math/grading; path dari input user tanpa `app/web/files.py` |
| Controller (`app/controllers`) | Panggil port/service yang di-inject; peringatan lewat `logging`; callback progress | `print` / `input()`; glob/parse artefak sendiri (pakai `functions/*_artifact.py`); import konstanta dari `app.services` |
| Services | Business logic + DI | Cetak ke stdout (kecuali logger) |
| Functions | Transform deterministik; baca/tulis artefak di modul yang disebut di [`conventions.md`](conventions.md#oop-dan-functional-programming) | Network, model, mutasi input |
| Interfaces | ABC/Protocol sempit | Implementasi konkret library |
| Models | Pydantic untuk semua kontrak antar layer (termasuk semua `*Result`); default bersama di `models/defaults.py` | Dataclass hasil di controller; literal `"1.5"` / `"student_001"` tersebar |

**Lapisan web.** `create_app` (`web/main.py`) menyimpan `WebState` (session, pipeline, jobs, templates) di `app.state`. `WebSession` memegang config + topik aktif (`explicit_topic_id` tetap `None` sampai user memilih topik). `WebPipeline` (`web/pipeline.py`) adalah façade: satu method per aksi halaman, wiring lewat `pipeline_factory.build_*` (yang di-patch di tes). Tahap panjang dijalankan `JobManager` (`web/jobs.py`): satu thread pekerja, satu job aktif per run (`JobAlreadyRunningError` → 409), progres `ProcessProgress` / pesan → `JobEvent`, dialirkan lewat SSE (`/jobs/<id>/events`, htmx-ext-sse) dan JSON (`/api/jobs/<id>`). `web/errors.py` memetakan `MathGraderError` ke status HTTP: flash partial dengan `HX-Retarget: #flash` untuk HTMX, JSON `{"detail"}` untuk `/api/*`, halaman error untuk navigasi biasa. `web/files.py` menolak path traversal dan membatasi upload (ukuran `web.max_upload_mb`, ekstensi).

## Peta folder

```text
app/
├── web/                   # main (create_app), __main__ (python -m app.web), session,
│                          # pipeline (WebPipeline), jobs (JobManager + SSE), files,
│                          # deps, errors, schemas, routers/, templates/, static/
│                          # (vendor: htmx, htmx-ext-sse, alpine, konva, katex)
├── exceptions.py          # MathGraderError + subclass domain
├── config/                # AppConfig + config.yaml (+ override env OLLAMA_*),
│                          # require_vision_model
├── controllers/           # render, recognize, extract, latex, validate, grade,
│                          # report, process, ingest_kunci, crop, question_label,
│                          # question_review
├── models/                # page, recognition (PageRecognition, SymbolicPayload, …),
│                          # question, question_crops (+ LabelSource,
│                          # QuestionLabelResult), question_review (ReviewFlag,
│                          # QuestionReviewResult), crop, standards, exam_schema,
│                          # latex, latex_report, validation, grading, report,
│                          # process, defaults
├── interfaces/            # PdfRenderer, VisionRecognizer, CropWorkspace,
│                          # QuestionLabeler, StepValidator, LlmClient,
│                          # GradeReporter, DetailedReporter, TopicPack, Capability,
│                          # QuestionGrader, QuestionExtractorPort,
│                          # LatexDocumentBuilder, LatexCompiler, KunciIngestPort
├── services/
│   ├── pipeline_factory.py  # wiring bersama web + resolusi topic pack
│   ├── pdf/                 # renderer (PyMuPDF)
│   ├── vision/              # ollama_client, recognizer, ink_region_proposer,
│   │                        # question_labeler, factory
│   ├── questions/           # extractor
│   ├── latex/               # builder, pdflatex_compiler (satu-satunya subprocess)
│   ├── math/                # parser, sympy_validator, equivalence, role_checks,
│   │                        # llm_judge, hybrid_validator
│   ├── grading/             # step_grader, rubric, standard_comparer,
│   │                        # feedback_annotator, report, latex_report
│   └── standards/           # kunci_ingester, standard_dir (topik_<bab>)
├── topics/                # topic pack: inequality_1_5 (1.5), abs_inequality_2 (2),
│                          # registry (_PACKS), runtime (pack aktif)
├── capabilities/          # registry 9 capability → rewrite_* di functions/*_normalize.py
├── functions/             # run_layout, question_crops, ink_layout, image_crop,
│                          # score_*, step_align, step_references, number_line,
│                          # kunci_ingest, standards_layout,
│                          # latex_report, latex_compile, report_details, *_normalize,
│                          # sse, report_artifact, artifact_guard, grading_artifact,
│                          # validation_artifact, recognition_artifact,
│                          # question_review (+ _artifact),
│                          # workspace_reset (pengosongan per-run), …
├── prompts/               # crop_math, crop_label, validation, grading
└── templates/             # report.html.j2, report.tex.j2
```

## Topic packs & capabilities

Kosakata grading / ingest / role berbasis **topic pack** (`app/topics/`). Daftar pack dan capability: [`math-topics.md`](math-topics.md).

Urutan resolusi pack (`resolve_topic_pack` di `pipeline_factory`):

1. topik yang dipilih user di dropdown **Topik** (`WebSession.explicit_topic_id`);
2. `topic_id` di `exam_schema.json` folder standar;
3. `grading.topic_id` di `config.yaml` (default `1.5`).

**Folder standar per topik.** Folder kunci/rubric/schema diturunkan dari topik (parameter `standard_dir` pada builder hanya untuk tes / override eksplisit): `resolve_standard_dir` (`services/standards/standard_dir.py`) mengembalikan `<grading.standards_root>/topik_<bab>`. Nama folder berasal dari fungsi pure `functions/standards_layout.standards_folder_name` (bab = bagian id sebelum titik, jadi `1.5` → `topik_1`). `topics/registry.py` menolak saat import dua pack yang memetakan ke folder yang sama. Semua builder di `pipeline_factory` (dan `vision/factory`) memakai resolusi ini, sehingga ingest dan grading satu topik selalu membaca folder yang sama. `WebSession` menyinkronkan `grading.topic_id` dengan topik aktif.

Ingest kunci (`POST /kunci/ingest`) melewati langkah 2 (schema lama bisa basi) dan menulis `topic_id` baru ke `exam_schema.json`. Satu ingest memakai tepat satu `.tex`; `KunciIngester` mengosongkan `solutions/question_*.tex` dan `rubrics/question_*.json` lama di folder topiknya sebelum menulis. Pack mendeklarasikan `capability_ids` yang dipakai `math_normalize`, serta `step_checks` (role → `StepCheck`) yang di-inject `pipeline_factory.build_validator(config, pack)` ke `SymPyStepValidator` / `HybridStepValidator`. Validator hanya mengenal `StepCheck`, bukan nama role; langkah acuan dipilih fungsi pure `functions/step_references.py`, cek SymPy per jenis ada di `services/math/role_checks.py`.

Inti pipeline (controller MVC) tetap **pack-agnostic**; bab baru menambah pack (+ capability bila perlu), bukan menulis ulang inti.

## Audit trail

Setiap keputusan skor harus dapat ditelusuri lewat artefak (daftar field: [`conventions.md`](conventions.md#jejak-audit)). Jangan hapus artefak intermediate **di tengah run** jika satu tahap gagal.

Artefak disimpan per PDF di `<output.root_dir>/<nama_pdf>/{pages,crops,recognition,questions}` + `report.json`, `summary.csv`, `report.html`, `report.tex`. `report.tex` dibangun dari view-model murni `app/functions/latex_report.py` (model di `app/models/latex_report.py`, input dari `app/functions/report_details.py`) lalu dirender `LatexReportWriter` (`DetailedReporter`) lewat `app/templates/report.tex.j2`; `ReportController` menerimanya lewat DI, begitu pula `PromptVersions` (dari `pipeline_factory.current_prompt_versions`). Setelah `report.tex` ditulis, `ReportController` memanggil `LatexCompiler` (port, opsional) yang diimplementasikan `PdfLatexCompiler` (`services/latex/pdflatex_compiler.py`, dibangun `pipeline_factory.build_pdf_compiler` dari `config.report.pdf`). Kompilasi dijalankan `passes` kali di folder run dengan jobname `report_build`, lalu `os.replace` ke `report.pdf`, sehingga PDF lama yang sedang dibuka viewer tidak memblokir pdflatex. `report.log` disimpan dan junk dihapus. Bagian pure (command, ringkasan error log, daftar junk) ada di `functions/latex_compile.py`. `ReportPdfError` hanya ditampilkan sebagai peringatan, dan `report_pdf_path` di `ReportResult` / `ProcessResult` bernilai `None` bila gagal. `ReportController` dan `ValidateController` membaca/menulis artefak lewat `functions/grading_artifact.py` / `functions/validation_artifact.py`, dan memastikan artefak sumber tidak berubah dengan `functions/artifact_guard.py`.

**Nama folder run** (`app/functions/run_layout.py`, `RunLayout`): stem PDF dengan karakter ilegal Windows diganti `_`. Nama kosong → `run`; nama yang bentrok dengan `standards` atau nama perangkat Windows (`con`, `nul`, `com1`, …) diberi sufiks `_run`. `list_run_dirs` hanya menganggap folder yang punya salah satu subfolder run.

Aturan pengosongan output: [README root](../README.md#artefak).

## Kontrak web

```text
python -m app.web [--config path] [--host H] [--port P]   # default web.host/web.port (127.0.0.1:8000)
```

| Route | Isi |
|-------|-----|
| `GET /` | Dashboard: topik, kunci (upload + ingest), PDF (upload + Propose crops), daftar run |
| `POST /topic`, `POST /kunci/upload`, `POST /kunci/ingest`, `POST /pdfs/upload` | Aksi dashboard (redirect 303 / `HX-Redirect`) |
| `POST /pdfs/propose` | Job: kosongkan folder run PDF itu, render, usulkan kotak ink → editor crop |
| `GET /runs/<run>` | Ringkasan run + langkah berikutnya |
| `GET /runs/<run>/crops`, `GET/PUT /api/runs/<run>/pages/<n>/regions` | Editor crop Konva; PUT = simpan kotak manual + crop ulang (padding 0) |
| `GET /runs/<run>/labels`, `POST /runs/<run>/labels/detect`, `POST /runs/<run>/labels` | Nomor soal per crop (job deteksi / simpan form `crop:<nama>`) |
| `POST /runs/<run>/transcribe` | Job: recognize + extract dari crop, berhenti sebelum grading → Review |
| `GET /runs/<run>/review`, `PUT /api/runs/<run>/questions/<id>`, `POST /api/preview` | Review `question.json` + preview KaTeX dari `symbolic` |
| `POST /runs/<run>/finish`, `POST /runs/<run>/finish-questions` | Job: grading penuh dari crop / dari `question.json` hasil review → Hasil |
| `GET /runs/<run>/results`, `GET /runs/<run>/files/<kind>` | Halaman hasil + unduh `report.pdf/html/tex/json`, `summary.csv` |
| `GET /jobs/<id>`, `GET /jobs/<id>/events`, `GET /api/jobs/<id>` | Halaman job, stream SSE, status JSON |
| `POST /api/process` | Body `{"pdf", "student_id"}`; seluruh pipeline tanpa berhenti di review sebagai job → 202 `{job_id, run, status_url}` |
| `GET /api/results/<question_id>?run=<nama_pdf>` | `grading.json` satu soal (`question_003` atau `3`); 404 bila belum ada |
| `GET /health` | `{"status": "ok"}` |

Router tipis: parse → `WebPipeline` / job → template atau JSON. `MathGraderError` → 4xx dengan pesan domain (flash / JSON), error tak terduga di job di-log dengan traceback (`logger.exception`) dan tampil sebagai "Gagal" di halaman job. `config.yaml` yang rusak (YAML tidak terbaca, isi teratas bukan mapping, tipe salah) dan env `OLLAMA_TIMEOUT_SECONDS` / `OLLAMA_MAX_RETRIES` yang bukan angka → `ConfigInvalidError`, dan `python -m app.web` keluar dengan kode 1. Path override di luar folder run yang sudah berisi file → `UnsafeOutputDirError`; pengecekannya ada di `functions/workspace_reset.ensure_resettable_dir`.
