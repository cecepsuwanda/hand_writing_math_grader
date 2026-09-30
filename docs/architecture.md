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
  → gabung per soal → student.tex → validasi SymPy (± LLM) → grading → report
```

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
| Controller | Panggil port/service yang di-inject, panggil view (termasuk prompt interaktif konfirmasi crop/label) | Logika math/prompt grading; `input()`; glob/parse artefak sendiri (pakai `functions/*_artifact.py`); import konstanta dari `app.services` |
| Services | Business logic + DI | Cetak ke stdout (kecuali logger) |
| Functions | Transform deterministik; baca/tulis artefak di modul yang disebut di [`conventions.md`](conventions.md#oop-dan-functional-programming) | Network, model, mutasi input |
| Interfaces | ABC/Protocol sempit | Implementasi konkret library |
| Models | Pydantic untuk semua kontrak antar layer (termasuk semua `*Result`); default bersama di `models/defaults.py` | Dataclass hasil di controller; literal `"1.5"` / `"student_001"` tersebar |

**Menu interaktif.** `cli.py` hanya parse argumen dan memilih handler (`_HANDLERS`). Menu `menu` dijalankan `MenuController` (`controllers/menu_controller.py`): state di `MenuSession` (topik, topik eksplisit, run aktif, exit code terakhir), dispatch lewat tabel `MenuChoice → handler`, dan pemetaan error → exit code lewat `exit_code_for`. Langkah ber-efek samping di balik port `MenuActions` (`interfaces/menu_actions.py`) yang diimplementasikan `_CliMenuActions` di `cli.py` dengan flow yang sama dengan subcommand (`_propose_crops`, `_recrop`, `_label`, `_finish_from_crops`). Label dan nomor menu berasal dari satu tabel `MAIN_MENU` di `functions/menu_choices.py`.

## Peta folder

```text
app/
├── cli.py                 # argparse (_add_<cmd>_parser) + _HANDLERS + flow bersama
│                          # menu/subcommand + _CliMenuActions
├── api.py                 # adapter FastAPI opsional (bukan pengganti CLI)
├── exceptions.py          # MathGraderError + subclass domain
├── config/                # AppConfig + config.yaml (+ override env OLLAMA_*),
│                          # require_vision_model
├── controllers/           # render, recognize, extract, latex, validate, grade,
│                          # report, process, ingest_kunci, crop, question_label,
│                          # menu (MenuController + MenuSession)
├── views/                 # progress, result, error, selection, exit, style,
│                          # crop, question_crops, prompt (input bersama)
├── models/                # page, recognition (PageRecognition, SymbolicPayload, …),
│                          # question, question_crops (+ LabelSource, LabelMode,
│                          # QuestionLabelResult), crop, standards, exam_schema,
│                          # latex, latex_report, validation, grading, report,
│                          # process, defaults
├── interfaces/            # PdfRenderer, VisionRecognizer, CropWorkspace,
│                          # QuestionLabeler, StepValidator, LlmClient,
│                          # GradeReporter, DetailedReporter, TopicPack, Capability,
│                          # QuestionGrader, QuestionExtractorPort,
│                          # LatexDocumentBuilder, KunciIngestPort, MenuActions
├── services/
│   ├── pipeline_factory.py  # wiring bersama CLI/API + resolusi topic pack
│   ├── pdf/                 # renderer (PyMuPDF)
│   ├── vision/              # ollama_client, recognizer, ink_region_proposer,
│   │                        # question_labeler, factory
│   ├── questions/           # extractor
│   ├── latex/               # builder
│   ├── math/                # parser, sympy_validator, equivalence, llm_judge,
│   │                        # hybrid_validator
│   ├── grading/             # step_grader, rubric, standard_comparer,
│   │                        # feedback_annotator, report, latex_report
│   └── standards/           # kunci_ingester
├── topics/                # topic pack: inequality_1_5 (1.5), abs_inequality_2 (2),
│                          # registry (_PACKS), runtime (pack aktif)
├── capabilities/          # registry 9 capability → rewrite_* di functions/*_normalize.py
├── functions/             # run_layout, question_crops, ink_layout, image_crop,
│                          # score_*, step_align, number_line, kunci_ingest,
│                          # latex_report, report_details, *_normalize,
│                          # menu_choices, artifact_guard, grading_artifact,
│                          # validation_artifact, recognition_artifact,
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

`ingest-kunci` melewati langkah 2 (schema lama bisa basi) dan menulis `topic_id` baru ke `exam_schema.json`. Pack mendeklarasikan `capability_ids` yang dipakai `math_normalize`.

Inti pipeline (controller MVC) tetap **pack-agnostic**; bab baru menambah pack (+ capability bila perlu), bukan menulis ulang inti.

## Audit trail

Setiap keputusan skor harus dapat ditelusuri lewat artefak (daftar field: [`conventions.md`](conventions.md#jejak-audit)). Jangan hapus artefak intermediate **di tengah run** jika satu tahap gagal.

Artefak disimpan per PDF di `<output.root_dir>/<nama_pdf>/{pages,crops,recognition,questions}` + `report.json`, `summary.csv`, `report.html`, `report.tex`. `report.tex` dibangun dari view-model murni `app/functions/latex_report.py` (model di `app/models/latex_report.py`, input dari `app/functions/report_details.py`) lalu dirender `LatexReportWriter` (`DetailedReporter`) lewat `app/templates/report.tex.j2`; `ReportController` menerimanya lewat DI, begitu pula `PromptVersions` (dari `pipeline_factory.current_prompt_versions`). `ReportController` dan `ValidateController` membaca/menulis artefak lewat `functions/grading_artifact.py` / `functions/validation_artifact.py`, dan memastikan artefak sumber tidak berubah dengan `functions/artifact_guard.py`.

**Nama folder run** (`app/functions/run_layout.py`, `RunLayout`): stem PDF dengan karakter ilegal Windows diganti `_`. Nama kosong → `run`; nama yang bentrok dengan `standards` atau nama perangkat Windows (`con`, `nul`, `com1`, …) diberi sufiks `_run`. `list_run_dirs` hanya menganggap folder yang punya salah satu subfolder run.

Aturan pengosongan output: [README root](../README.md#artefak).

## Kontrak CLI

```text
python -m app.cli [--config path] <subcommand> ...

menu                         [--topic ID]      # 8 pilihan, lihat README
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
latex                        [--run] [--questions-dir]
validate                     [--run] [--questions-dir] [--topic]
grade                        [--run] [--questions-dir] [--standard] [--topic]
report                       [--run] [--questions-dir] [--output] [--student-id] [--standard]
```

Subcommand tipis: parse → controller (dari `pipeline_factory.build_*`) → view → exit code. Exit code: `0` sukses, `1` `MathGraderError`, `2` error tak terduga (di-log dengan traceback lewat `logger.exception`). `menu` tanpa terminal interaktif → `InteractiveTerminalRequiredError` (exit 1).

## API (opsional)

`python -m app.api` (FastAPI, wiring sama lewat `pipeline_factory`):

| Endpoint | Isi |
|----------|-----|
| `GET /health` | `{"status": "ok"}` |
| `POST /api/process` | Body `{"pdf", "student_id"}`; jalankan `process` tanpa prompt (`force_yes`). `MathGraderError` → 422 |
| `GET /api/results/{question_id}?run=<nama_pdf>` | `grading.json` satu soal (`question_003` atau `3`) dari run tersebut; 404 bila belum ada |
