# Arsitektur

## Prinsip wajib

Proyek ini wajib memakai **MVC**, **SOLID**, **clean code**, serta **OOP** berdampingan dengan **functional programming**. Ringkasan dan larangan: [`conventions.md`](conventions.md). Spesifikasi lengkap: [`plan_ai_math_grader_ollama.md`](plan_ai_math_grader_ollama.md) §2.4 / §3.2.

## Pipeline

```text
PDF → page images → Vision recognition → structured JSON
  → question/step extraction → student LaTeX
  → validation (SymPy step consistency, lalu LLM jika uncertain)
  → rubric grading → report + CLI summary
```

Recognition dan grading **dipisah**. Jangan minta LLM memberi nilai langsung dari gambar.

**Status validasi saat ini:** konsistensi langkah mahasiswa (parse + ekivalensi SymPy antar langkah / final). **Compare final answer** ke `standards/.../solutions/question_NNN.tex` (marker `% final answer`) dan **step-align sequential** ke baris `aligned`/`align` dijalankan saat grading via SymPy equivalence (skor = min(konsistensi, standard)). Folder `data/input/kunci_jawaban/` dapat di-ingest ke solutions via CLI `ingest-kunci` (slice: enumerate + align + HP; bukan parser LaTeX arbitrary). Opsional HTTP: `app/api.py` (FastAPI) memanggil controller yang sama; CLI tetap entry wajib.

## Lapisan MVC

```text
View (CLI)          → progress, ringkasan skor, error, path output
Controller          → parse args, orkestrasi, map exception → pesan
Model + Services    → domain, use-case, pure functions, ports
Infrastructure      → Ollama, PyMuPDF, SymPy, filesystem, config
```

**Arah ketergantungan:** View → Controller → Services/Models → Infrastructure.

Infrastructure **tidak** bergantung pada Controller atau View.

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
├── config/                # AppConfig + config.yaml
├── controllers/           # render, recognize, validate, grade, process
├── views/                 # progress, result, error
├── models/                # Page, Recognition, Question, Validation, Grade
├── services/
│   ├── pdf/               # renderer
│   ├── vision/            # ollama_client, recognizer
│   ├── questions/         # extractor
│   ├── latex/             # builder
│   ├── math/              # parser, sympy_validator, equivalence
│   ├── grading/           # step_grader, rubric, report
│   └── workspace/         # output cleaner
├── functions/             # latex_transforms, score_aggregate, paths (pure)
├── interfaces/            # PdfRenderer, VisionRecognizer, StepValidator, GradeReporter
└── prompts/               # recognition, latex, validation, grading
```

## Audit trail

Setiap keputusan skor harus menyimpan bukti: gambar, recognition, LaTeX mahasiswa, hasil SymPy/LLM, alasan, skor, confidence, referensi halaman. Referensi jawaban standar (final) tercatat di `grading.json` sebagai `standard_final_status` bila solution `.tex` tersedia.

Jangan hapus artefak intermediate **di tengah run** jika satu tahap gagal.

Awal perintah `process` mengosongkan `data/output/` (kecuali `standards/`) agar run baru bersih.

## Kontrak CLI

```text
python -m app.cli process                 # pilih PDF dari data/input/jawaban
python -m app.cli process file.pdf
python -m app.cli render|recognize|extract|validate|grade|report ...
```

Subcommand tipis: parse → controller → view → exit code (`0` sukses).
