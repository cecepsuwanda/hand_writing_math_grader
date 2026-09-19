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

## Status

Spesifikasi dan panduan agent sudah ada. MVP domain: **pertidaksamaan (topik 1.5)**. Implementasi kode mengikuti `docs/development-phases.md`.

## Agent guidance

- Cursor rules: `.cursor/rules/`
- Skills: `.cursor/skills/`
