# Arsitektur

## Prinsip wajib

Proyek ini wajib memakai **MVC**, **SOLID**, **clean code**, serta **OOP** berdampingan dengan **functional programming**. Aturan coding dan domain: [`conventions.md`](conventions.md). Pemakaian CLI: [README root](../README.md).

## Pipeline

```text
PDF → page images
  → ink-cluster bboxes (deterministik; Pillow)
  → tulis page_NNN_regions.json (editable) + crop Pillow
  → konfirmasi user / edit JSON / recrop (CLI propose-crops | recrop; --yes melewati)
  → [manual] crop_label VLM → crops/question_crops/question_NNN.json
    → konfirmasi user / edit JSON / muat ulang (CLI label-questions | relabel-questions)
  → crop_math VLM (nomor soal dari question_crops bila ada) → symbolic JSON (+ latex_source.tex)
  → gabung per soal → questions/question_NNN/question.json
    → tinjau transkripsi / edit JSON / muat ulang (process; --yes melewati)
  → student.tex → validasi SymPy (± LLM) → grading → report
  → pdflatex report.tex → report.pdf (gagal = peringatan saja)
```

**Tinjau `question.json`.** Setelah Extract, `ProcessController` memanggil `QuestionReviewController.review_loop` (pola sama dengan `confirm_loop`): ringkasan per langkah (`role`, `raw_text`, `symbolic.repr`) beserta tanda `low_confidence` (< `recognition.review_min_confidence`), `uncertain_mark` (`[uncertain` di `raw_text`), dan `missing_symbolic` (`repr` kosong, kecuali `kind: figure`), lalu tanya y/n; jika n, tunggu edit lalu muat ulang. Penanda dihitung pure di `functions/question_review.py`; baca, sidik jari (sha256), dan penghapusan sidecar ada di `functions/question_review_artifact.py`. Soal yang berubah kehilangan `latex_source.tex` agar `student.tex` dibangun ulang dari langkah hasil edit. JSON yang tidak terbaca atau `question_id` yang tidak sama dengan nama folder: ditanya ulang saat interaktif, dan menghentikan run (`QuestionArtifactsInvalidError`) saat `--yes` / non-TTY / API. Tahap ini bukan `ProcessStage` tersendiri; progres tetap 7 tahap.

**Lanjut dari `question.json` yang sudah diedit (menu 8 / `finish-questions`).** `ProcessController.process_from_questions` berbagi ekor pipeline (`_run_from_questions`: tinjau → LaTeX → validasi → grading → report) dengan `process` dan `process_from_crops`, tetapi tidak menjalankan recognize/extract dan tidak mengosongkan `questions/`, jadi `question.json` hanya dibaca. Sebelum tinjau, `QuestionReviewController.prune_stale_latex_sources` menghapus `latex_source.tex` yang lebih lama (mtime) dari `question.json`-nya. Aturan ini aman karena Extract menulis `question.json` lebih dulu. Folder tanpa `question.json` → `QuestionsNotFoundError`. Progres dimulai dari LATEX (4/7), dan tahap ini tidak butuh model vision.

Recognition dan grading **dipisah**. JSON soal menyimpan `raw_text` + `symbolic` (bukan LaTeX). LaTeX hanya di artefak `.tex`. Satu crop boleh menghasilkan beberapa soal bila ink menggabungkan jawaban dan model mengembalikan `{"questions":[...]}`.

**Nomor soal per crop (`question_crops/`).** Format file dan alur user: [README root](../README.md#nomor-soal-question_crops). Aturan internal: `label-questions` menulis satu file per soal di kunci; crop tanpa label mewarisi soal sebelumnya dalam urutan baca (halaman, lalu `order`). `relabel-questions` memvalidasi: soal di luar kunci atau nama crop tak dikenal = error; soal tanpa crop atau crop tanpa soal = peringatan. Saat recognition, satu nomor yang ditetapkan user dipaksakan, beberapa nomor membatasi pilihan model, dan soal yang tersebar di beberapa crop tidak di-demote sebagai duplikat. File yang tidak valid menghentikan run (`QuestionCropsInvalidError`); folder yang belum ada hanya memicu peringatan.

`exam_schema.json`: recognition (crop_math dan crop_label) hanya menerima **stem + flag `expects_figure`**; `steps` / `final` / `HP` / `number_line` / `parts` hanya untuk grading.

Aturan validasi dan grading: [`conventions.md`](conventions.md#validasi-dan-grading).

## Lapisan MVC

```text
View (CLI)          → progress, ringkasan skor, error, path output, prompt interaktif
Controller          → orkestrasi use-case, pilih view, map exception → pesan
Model + Services    → domain, use-case, pure functions, ports
Infrastructure      → Ollama, PyMuPDF, SymPy, filesystem, config
```

**Arah ketergantungan:** View → Controller → Services/Models → Infrastructure.

| Layer | Boleh | Tidak boleh |
|-------|--------|-------------|
| View | Format teks terminal; baca input hanya lewat `views/prompt_view.py` (`read_line`, `ask_yes_no`, `prompt_choice`, `wait_for_edit`); error/peringatan ke stderr (`error_view`) | Panggil Ollama/SymPy/persist; import `app.controllers` / `app.services` |
| Controller | Panggil port/service yang di-inject, panggil view (termasuk prompt interaktif konfirmasi crop/label/transkripsi) | Logika math/prompt grading; `input()`; glob/parse artefak sendiri (pakai `functions/*_artifact.py`); import konstanta dari `app.services` |
| Services | Business logic + DI | Cetak ke stdout (kecuali logger) |
| Functions | Transform deterministik; baca/tulis artefak di modul yang disebut di [`conventions.md`](conventions.md#oop-dan-functional-programming) | Network, model, mutasi input |
| Interfaces | ABC/Protocol sempit | Implementasi konkret library |
| Models | Pydantic untuk semua kontrak antar layer (termasuk semua `*Result`); default bersama di `models/defaults.py` | Dataclass hasil di controller; literal `"1.5"` / `"student_001"` tersebar |

**Subcommand dan menu interaktif.** `cli.py` hanya membangun parser dari `COMMANDS` (`commands/__init__.py`) dan memanggil `Command.run` milik subcommand terpilih. Setiap subcommand adalah satu class `Command` (`commands/base.py`: `name`, `help`, `configure(parser)`, `run(args)`) di `commands/stages.py`, `commands/crops.py`, atau `commands/workflows.py`; builder dipanggil lewat modul `pipeline_factory.build_*`. Menu `menu` dijalankan `MenuController` (`controllers/menu_controller.py`): state di `MenuSession` (topik, topik eksplisit, run aktif, exit code terakhir), dispatch lewat tabel `MenuChoice → handler`, dan pemetaan error → exit code lewat `exit_code_for`. Langkah ber-efek samping di balik port `MenuActions` (`interfaces/menu_actions.py`) yang diimplementasikan `CliMenuActions` (`commands/menu_actions.py`) dengan flow yang sama dengan subcommand di `commands/flows.py` (`propose_crops`, `recrop`, `label`, `finish_from_crops`, `finish_from_questions`). Label dan nomor menu berasal dari satu tabel `MAIN_MENU` di `functions/menu_choices.py`.

## Peta folder

```text
app/
├── cli.py                 # bootstrap: build_parser + main atas COMMANDS
├── commands/              # base (Command + helper argumen), stages, crops,
│                          # workflows, flows (alur bersama menu/subcommand +
│                          # report_failure), menu_actions (CliMenuActions)
├── api.py                 # adapter FastAPI opsional (bukan pengganti CLI)
├── exceptions.py          # MathGraderError + subclass domain
├── config/                # AppConfig + config.yaml (+ override env OLLAMA_*),
│                          # require_vision_model
├── controllers/           # render, recognize, extract, latex, validate, grade,
│                          # report, process, ingest_kunci, crop, question_label,
│                          # question_review, menu (MenuController + MenuSession)
├── views/                 # progress, result, error, selection, exit, style,
│                          # crop, question_crops, question_review,
│                          # prompt (input bersama)
├── models/                # page, recognition (PageRecognition, SymbolicPayload, …),
│                          # question, question_crops (+ LabelSource, LabelMode,
│                          # QuestionLabelResult), question_review (ReviewFlag,
│                          # QuestionReviewResult), crop, standards, exam_schema,
│                          # latex, latex_report, validation, grading, report,
│                          # process, defaults
├── interfaces/            # PdfRenderer, VisionRecognizer, CropWorkspace,
│                          # QuestionLabeler, StepValidator, LlmClient,
│                          # GradeReporter, DetailedReporter, TopicPack, Capability,
│                          # QuestionGrader, QuestionExtractorPort,
│                          # LatexDocumentBuilder, LatexCompiler, KunciIngestPort,
│                          # MenuActions
├── services/
│   ├── pipeline_factory.py  # wiring bersama CLI/API + resolusi topic pack
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
│                          # menu_choices, artifact_guard, grading_artifact,
│                          # validation_artifact, recognition_artifact,
│                          # question_review (+ _artifact),
│                          # workspace_reset (pengosongan per-run), …
├── prompts/               # crop_math, crop_label, validation, grading
└── templates/             # report.html.j2, report.tex.j2
```

## Topic packs & capabilities

Kosakata grading / ingest / role berbasis **topic pack** (`app/topics/`). Daftar pack dan capability: [`math-topics.md`](math-topics.md).

Urutan resolusi pack (`resolve_topic_pack` di `pipeline_factory`):

1. `--topic ID` (atau pilihan menu **Pilih topik**);
2. `topic_id` di `exam_schema.json` dari `--standard`;
3. `grading.topic_id` di `config.yaml` (default `1.5`).

**Folder standar per topik.** Tanpa `--standard`, folder kunci/rubric/schema diturunkan dari topik: `resolve_standard_dir` (`services/standards/standard_dir.py`) mengembalikan `<grading.standards_root>/topik_<bab>`. Nama folder berasal dari fungsi pure `functions/standards_layout.standards_folder_name` (bab = bagian id sebelum titik, jadi `1.5` → `topik_1`). `topics/registry.py` menolak saat import dua pack yang memetakan ke folder yang sama. Semua builder di `pipeline_factory` (dan `vision/factory`) memakai resolusi ini, sehingga ingest dan grading satu topik selalu membaca folder yang sama. Menu menyinkronkan `grading.topic_id` dengan topik sesi.

`ingest-kunci` melewati langkah 2 (schema lama bisa basi) dan menulis `topic_id` baru ke `exam_schema.json`. Satu ingest memakai tepat satu `.tex`; `KunciIngester` mengosongkan `solutions/question_*.tex` dan `rubrics/question_*.json` lama di folder topiknya sebelum menulis. Pack mendeklarasikan `capability_ids` yang dipakai `math_normalize`, serta `step_checks` (role → `StepCheck`) yang di-inject `pipeline_factory.build_validator(config, pack)` ke `SymPyStepValidator` / `HybridStepValidator`. Validator hanya mengenal `StepCheck`, bukan nama role; langkah acuan dipilih fungsi pure `functions/step_references.py`, cek SymPy per jenis ada di `services/math/role_checks.py`.

Inti pipeline (controller MVC) tetap **pack-agnostic**; bab baru menambah pack (+ capability bila perlu), bukan menulis ulang inti.

## Audit trail

Setiap keputusan skor harus dapat ditelusuri lewat artefak (daftar field: [`conventions.md`](conventions.md#jejak-audit)). Jangan hapus artefak intermediate **di tengah run** jika satu tahap gagal.

Artefak disimpan per PDF di `<output.root_dir>/<nama_pdf>/{pages,crops,recognition,questions}` + `report.json`, `summary.csv`, `report.html`, `report.tex`. `report.tex` dibangun dari view-model murni `app/functions/latex_report.py` (model di `app/models/latex_report.py`, input dari `app/functions/report_details.py`) lalu dirender `LatexReportWriter` (`DetailedReporter`) lewat `app/templates/report.tex.j2`; `ReportController` menerimanya lewat DI, begitu pula `PromptVersions` (dari `pipeline_factory.current_prompt_versions`). Setelah `report.tex` ditulis, `ReportController` memanggil `LatexCompiler` (port, opsional) yang diimplementasikan `PdfLatexCompiler` (`services/latex/pdflatex_compiler.py`, dibangun `pipeline_factory.build_pdf_compiler` dari `config.report.pdf`). Kompilasi dijalankan `passes` kali di folder run dengan jobname `report_build`, lalu `os.replace` ke `report.pdf`, sehingga PDF lama yang sedang dibuka viewer tidak memblokir pdflatex. `report.log` disimpan dan junk dihapus. Bagian pure (command, ringkasan error log, daftar junk) ada di `functions/latex_compile.py`. `ReportPdfError` hanya ditampilkan sebagai peringatan, dan `report_pdf_path` di `ReportResult` / `ProcessResult` bernilai `None` bila gagal. `ReportController` dan `ValidateController` membaca/menulis artefak lewat `functions/grading_artifact.py` / `functions/validation_artifact.py`, dan memastikan artefak sumber tidak berubah dengan `functions/artifact_guard.py`.

**Nama folder run** (`app/functions/run_layout.py`, `RunLayout`): stem PDF dengan karakter ilegal Windows diganti `_`. Nama kosong → `run`; nama yang bentrok dengan `standards` atau nama perangkat Windows (`con`, `nul`, `com1`, …) diberi sufiks `_run`. `list_run_dirs` hanya menganggap folder yang punya salah satu subfolder run.

Aturan pengosongan output: [README root](../README.md#artefak).

## Kontrak CLI

```text
python -m app.cli [--config path] <subcommand> ...

menu                         [--topic ID]      # 9 pilihan, lihat README
process [file.pdf]           [--topic] [--standard] [--output] [--student-id] [--dpi]
                             [--pages-dir] [--recognition-dir] [--questions-dir]
                             [--yes] [--use-existing-crops]
ingest-kunci [kunci.tex]     [--topic] [--standard] [--kunci-dir]
render file.pdf              [--output] [--dpi]
propose-crops file.pdf       [--pages-dir] [--dpi] [--yes]
recognize file.pdf           [--output] [--pages-dir] [--dpi] [--yes] [--use-existing-crops]
extract file.pdf             [--output] [--recognition-dir] [--pages-dir] [--dpi]
                             [--force-recognize]
recrop                       [--run] [--pages-dir] [--yes]
label-questions              [--run] [--yes]
relabel-questions            [--run] [--yes]
finish-questions             [--run] [--topic] [--yes]   # = menu 8
latex                        [--run] [--questions-dir]
validate                     [--run] [--questions-dir] [--topic]
grade                        [--run] [--questions-dir] [--standard] [--topic]
report                       [--run] [--questions-dir] [--output] [--student-id] [--standard]
```

Subcommand tipis: parse → controller (dari `pipeline_factory.build_*`) → view → exit code. Exit code: `0` sukses, `1` `MathGraderError`, `2` error tak terduga (di-log dengan traceback lewat `logger.exception`). `config.yaml` yang rusak (YAML tidak terbaca, isi teratas bukan mapping, tipe salah) dan env `OLLAMA_TIMEOUT_SECONDS` / `OLLAMA_MAX_RETRIES` yang bukan angka → `ConfigInvalidError` (exit 1). Path override di luar folder run yang sudah berisi file → `UnsafeOutputDirError` (exit 1); pengecekannya ada di `functions/workspace_reset.ensure_resettable_dir`. `menu` tanpa terminal interaktif → `InteractiveTerminalRequiredError` (exit 1).

## API (opsional)

`python -m app.api` (FastAPI, wiring sama lewat `pipeline_factory`):

| Endpoint | Isi |
|----------|-----|
| `GET /health` | `{"status": "ok"}` |
| `POST /api/process` | Body `{"pdf", "student_id"}`; jalankan `process` tanpa prompt (`force_yes`). `MathGraderError` → 422 |
| `GET /api/results/{question_id}?run=<nama_pdf>` | `grading.json` satu soal (`question_003` atau `3`) dari run tersebut; 404 bila belum ada |
