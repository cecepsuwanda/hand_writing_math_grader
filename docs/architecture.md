# Arsitektur

## Prinsip wajib

Proyek ini wajib memakai **MVC**, **SOLID**, **clean code**, serta **OOP** berdampingan dengan **functional programming**. Ringkasan dan larangan: [`conventions.md`](conventions.md). Spesifikasi lengkap: [`plan_ai_math_grader_ollama.md`](plan_ai_math_grader_ollama.md) §2.4 / §3.2.

## Pipeline

```text
PDF → page images
  → ink-cluster bboxes (deterministic; Pillow)
  → write editable page_NNN_regions.json + Pillow crops
  → human confirm / edit JSON / recrop (CLI propose-crops | recrop; --yes skips)
  → crop_math VLM → symbolic JSON (+ latex_source.tex)
  → question merge → student.tex → SymPy validation → grading → report
```

Recognition dan grading **dipisah**. JSON soal menyimpan `raw_text` + `symbolic` (bukan LaTeX). LaTeX hanya di artefak `.tex`. Satu crop boleh menghasilkan beberapa soal bila ink menggabungkan jawaban dan model mengembalikan `{"questions":[...]}`.

`exam_schema.json`: recognition memakai **stem + expects_figure (+ parts)** saja; `steps`/`final`/`HP`/`number_line` hanya untuk grading.

**Validasi:** konsistensi langkah mahasiswa (SymPy ± LLM). **Grading:** skor langkah = konsistensi; soft-align ke `exam_schema` / `standards/.../solutions` = audit; skor `final_answer` = min(konsistensi, standard SymPy). Ingest kunci: `ingest-kunci`. Opsional HTTP: `app/api.py` (wiring sama `pipeline_factory`); CLI tetap entry wajib.

## Lapisan MVC

```text
View (CLI)          → progress, ringkasan skor, error, path output
Controller          → parse args, orkestrasi, map exception → pesan
Model + Services    → domain, use-case, pure functions, ports
Infrastructure      → Ollama, PyMuPDF, SymPy, filesystem, config
```

**Arah ketergantungan:** View → Controller → Services/Models → Infrastructure.

| Layer | Boleh | Tidak boleh |
|-------|--------|-------------|
| View | Format teks terminal | Panggil Ollama/SymPy/persist |
| Controller | Panggil service, pilih view | Logika math/prompt grading |
| Services | Business logic + DI | Cetak ke stdout (kecuali logger) |
| Functions | Pure transform | I/O, network, mutasi input |
| Interfaces | ABC/Protocol sempit | Implementasi konkret library |

## Peta folder

```text
app/
├── cli.py                 # argparse bootstrap
├── api.py                 # optional FastAPI adapter (pasca-MVP)
├── config/                # AppConfig + config.yaml
├── controllers/           # render, recognize, extract, latex, validate,
│                          # grade, report, process, ingest_kunci
├── views/                 # progress, result, error, selection, exit, style
├── models/                # Page, Recognition, Question, ExamSchema, …
├── services/
│   ├── pipeline_factory.py  # shared CLI/API ProcessController wiring
│   ├── pdf/                 # renderer
│   ├── vision/              # ollama_client, recognizer, ink_region_proposer,
│   │                        # factory
│   ├── questions/           # extractor
│   ├── latex/               # builder
│   ├── math/                # parser, sympy_validator, equivalence, llm_judge
│   ├── grading/             # step_grader, rubric, standard_comparer, report
│   ├── standards/           # kunci_ingester
│   └── workspace/           # output cleaner (incl. crops_dir)
├── functions/             # ink_layout, image_crop, score_*, …
├── interfaces/            # PdfRenderer, VisionRecognizer, StepValidator, …
└── prompts/               # crop_math, validation, grading
```

## Audit trail

Setiap keputusan skor harus menyimpan bukti: gambar, crops/`*_regions*.json`, recognition, LaTeX mahasiswa, hasil SymPy/LLM, alasan, skor, confidence, referensi halaman.

Jangan hapus artefak intermediate **di tengah run** jika satu tahap gagal.

Awal perintah `process` mengosongkan `data/output/` (kecuali `standards/`) termasuk `crops/` bila di luar root.

## Kontrak CLI

```text
python -m app.cli menu                    # menu: ingest / crop ink / recrop / grading / keluar
python -m app.cli process                 # pilih PDF dari data/input/jawaban
python -m app.cli process file.pdf
python -m app.cli ingest-kunci            # tulis solutions/ + exam_schema.json
python -m app.cli render|recognize|extract|validate|grade|report ...
```

Subcommand tipis: parse → controller → view → exit code (`0` sukses).
