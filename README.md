# hand_writing_math_grader

Aplikasi **CLI Python** untuk memeriksa jawaban soal matematika tulisan tangan dari PDF (recognition → validasi SymPy/LLM → grading berbasis rubric).

## Dokumentasi

| Dokumen | Keterangan |
|---------|------------|
| [plan_ai_math_grader_ollama.md](docs/plan_ai_math_grader_ollama.md) | Spesifikasi lengkap |
| [topik.md](docs/topik.md) | Silabus domain matematika |
| [docs/README.md](docs/README.md) | Indeks panduan pengembangan |
| [docs/architecture.md](docs/architecture.md) | Arsitektur MVC + pipeline |
| [docs/development-phases.md](docs/development-phases.md) | Phase 1–9 |
| [docs/math-topics.md](docs/math-topics.md) | Status domain per bab |
| [docs/conventions.md](docs/conventions.md) | SOLID, clean coding, OOP+FP |

## Cara pakai singkat

1. Taruh PDF jawaban di `data/input/jawaban/`, kunci di `data/input/kunci_jawaban/`.
2. Jalankan pipeline (pilih PDF interaktif, atau sebutkan nama file):

```bash
python -m app.cli process
python -m app.cli process smoke_inequality.pdf
```

Di awal `process`, isi `data/output/` dikosongkan (kecuali `standards/`).

## Status

MVP domain: **pertidaksamaan (topik 1.5)**. Implementasi mengikuti `docs/development-phases.md`.

## Agent guidance

- Cursor rules: `.cursor/rules/`
- Skills: `.cursor/skills/`
