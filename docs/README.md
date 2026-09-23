# Dokumentasi Math Grader

Panduan pengembangan aplikasi CLI untuk menilai lembar jawaban matematika tulisan tangan (PDF → recognition → validasi → grading).

## Prinsip arsitektur

Wajib: **MVC**, **SOLID**, **clean code**, **OOP + functional programming**. Lihat [architecture.md](architecture.md) dan [conventions.md](conventions.md) (detail juga di [plan_ai_math_grader_ollama.md](plan_ai_math_grader_ollama.md) §2.4).

## Sumber kebenaran

| Dokumen | Isi |
|---------|-----|
| [plan_ai_math_grader_ollama.md](plan_ai_math_grader_ollama.md) | Spesifikasi lengkap pipeline, data model, fase, DoD |
| [topik.md](topik.md) | Silabus domain matematika (bab 1–11) |
| [architecture.md](architecture.md) | MVC, SOLID, clean code, OOP+FP, dependency direction, struktur folder |
| [development-phases.md](development-phases.md) | Phase 1–9 dan acceptance criteria |
| [math-topics.md](math-topics.md) | Status domain per bab + urutan implementasi |
| [conventions.md](conventions.md) | Prinsip arsitektur wajib, SOLID, clean coding, OOP+FP, larangan |

## Target MVP

CLI Python (MVC) untuk soal **pertidaksamaan (topik 1.5)**, 1–5 halaman:

```text
PDF → PNG → ink bbox → crop → Vision symbolic JSON
  → LaTeX artefak → SymPy (± LLM) → grade vs exam_schema → report
```

Roadmap domain mengikuti [`topik.md`](topik.md) / [math-topics.md](math-topics.md). Web UI / FastAPI **bukan** bagian MVP.

## Struktur aplikasi (target)

```text
app/
├── cli.py              # entry point
├── controllers/        # orkestrasi
├── views/              # presentasi CLI
├── models/             # schema domain
├── services/           # use-case + adapter
├── functions/          # pure transforms
├── interfaces/         # ports SOLID
└── prompts/
```

## Cara mulai (setelah kode ada)

Letakkan PDF jawaban di `data/input/jawaban/`. Jawaban standar per soal: `data/output/standards/<exam>/solutions/question_NNN.tex` (baris setelah `% final answer` dipakai compare SymPy saat `grade`). Ingest kunci: `python -m app.cli ingest-kunci` dari `data/input/kunci_jawaban/` (slice enumerate+align+HP; menimpa `solutions/` di `--standard`).

Opsional API: `python -m app.api` (FastAPI — bukan pengganti CLI).

Pilih aksi lewat menu utama (ingest kunci / proses PDF / keluar):

```bash
python -m app.cli menu
# atau: run.bat
```

Atau sebutkan file langsung:

```bash
python -m app.cli process smoke_inequality.pdf
python -m app.cli process data/input/jawaban/smoke_inequality.pdf \
  --standard data/output/standards/exam_001 \
  --output data/output
```

Setiap `process` mengosongkan `data/output/` dulu (kecuali `standards/`), lalu menulis artefak baru.

## Smoke live (Ollama)

Tidak dijalankan di CI/`pytest`. Syarat: Ollama listening + `vision_model` / `reasoning_model` di [`app/config/config.yaml`](../app/config/config.yaml).

```bash
# Interactive main menu (ingest kunci / process PDF / exit)
python -m app.cli menu

# Bare filename resolves under jawaban/
python -m app.cli process smoke_inequality.pdf

# Explicit paths
python -m app.cli process data/input/jawaban/smoke_inequality.pdf \
  --standard data/output/standards/exam_001 \
  --output data/output
```

Windows helper: [`scripts/smoke_live.bat`](../scripts/smoke_live.bat).

Expected: progress 7 tahap, ringkasan skor, artefak di `data/output/` (`report.json`, `summary.csv`, `report.html`, plus pages/recognition/questions).

## Panduan agent

- Rules: `.cursor/rules/`
- Skills: `.cursor/skills/implement-math-grader-phase`, `.cursor/skills/review-math-grader-compliance`
