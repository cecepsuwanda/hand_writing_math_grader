# Arsitektur

## Pipeline

```text
PDF → page images → Vision recognition → structured JSON
  → question/step extraction → student LaTeX
  → validation (SymPy, lalu LLM) → compare standard
  → rubric grading → report + CLI summary
```

Recognition dan grading **dipisah**. Jangan minta LLM memberi nilai langsung dari gambar.

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
│   ├── questions/         # segmenter, extractor
│   ├── latex/             # builder
│   ├── math/              # parser, sympy_validator, equivalence
│   └── grading/           # step_grader, rubric, report
├── functions/             # latex_transforms, score_aggregate, confidence
├── interfaces/            # PdfRenderer, VisionRecognizer, StepValidator, GradeReporter
└── prompts/               # recognition, latex, validation, grading
```

## Audit trail

Setiap keputusan skor harus menyimpan bukti: gambar, recognition, LaTeX mahasiswa, jawaban standar, hasil SymPy/LLM, alasan, skor, confidence, referensi halaman.

Jangan hapus artefak intermediate **di tengah run** jika satu tahap gagal.

Awal perintah `process` mengosongkan `data/output/` (kecuali `standards/`) agar run baru bersih.

## Kontrak CLI

```text
python -m app.cli process                 # pilih PDF dari data/input/jawaban
python -m app.cli process file.pdf
python -m app.cli render|recognize|extract|validate|grade|report ...
```

Subcommand tipis: parse → controller → view → exit code (`0` sukses).
